import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

function parseArgs(argv) {
  const values = {
    output: '.acceptance/million-gpu',
    expectedNodes: 1000001,
    expectedElements: 1000000,
    geometry: 'any',
    timeoutMs: 300000,
    headless: true,
    browser: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    playwrightRoot: process.env.PLAYWRIGHT_ROOT,
    session: path.join(os.homedir(), '.abaqus-mcp-pro', 'viewer-session.json'),
  };
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === '--task') { values.task = value; i += 1; }
    else if (key === '--output') { values.output = value; i += 1; }
    else if (key === '--expected-nodes') { values.expectedNodes = Number(value); i += 1; }
    else if (key === '--expected-elements') { values.expectedElements = Number(value); i += 1; }
    else if (key === '--geometry') { values.geometry = value; i += 1; }
    else if (key === '--timeout-ms') { values.timeoutMs = Number(value); i += 1; }
    else if (key === '--browser') { values.browser = value; i += 1; }
    else if (key === '--playwright-root') { values.playwrightRoot = value; i += 1; }
    else if (key === '--session') { values.session = value; i += 1; }
    else if (key === '--headed') values.headless = false;
    else if (key === '--headless') values.headless = true;
    else throw new Error(`Unknown argument: ${key}`);
  }
  if (!values.task) throw new Error('--task is required');
  if (!values.playwrightRoot) throw new Error('--playwright-root or PLAYWRIGHT_ROOT is required');
  if (!Number.isFinite(values.expectedNodes) || values.expectedNodes <= 0) {
    throw new Error('--expected-nodes must be positive');
  }
  if (!Number.isFinite(values.expectedElements) || values.expectedElements <= 0) {
    throw new Error('--expected-elements must be positive');
  }
  if (!['line', 'surface', 'any'].includes(values.geometry)) {
    throw new Error('--geometry must be line, surface, or any');
  }
  return values;
}

function percentile(values, fraction) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor((sorted.length - 1) * fraction))];
}

const args = parseArgs(process.argv.slice(2));
const outputDir = path.resolve(args.output);
await fs.mkdir(outputDir, { recursive: true });

const session = JSON.parse(await fs.readFile(path.resolve(args.session), 'utf8'));
assert.ok(session.url && session.token, 'viewer session is missing url or token');
const baseUrl = new URL(session.url);
const viewerBase = `${baseUrl.protocol}//${baseUrl.host}`;
const token = session.token;

const { chromium } = await import(pathToFileURL(path.join(args.playwrightRoot, 'index.mjs')).href);
const report = {
  schema_version: 1,
  started_at: new Date().toISOString(),
  task_id: args.task,
  expected: {
    nodes: args.expectedNodes,
    elements: args.expectedElements,
  },
  launch: {
    browser: args.browser,
    headless: args.headless,
    args: [
      '--disable-gpu-sandbox',
      '--ignore-gpu-blocklist',
      '--enable-gpu-rasterization',
      '--enable-zero-copy',
      '--use-angle=d3d11',
    ],
  },
  timings: {},
  gpu: {},
  renderer: {},
  interaction: {},
  pixels: {},
  console_errors: [],
  page_errors: [],
  screenshots: [],
};

let browser;
let page;
try {
  browser = await chromium.launch({
    executablePath: args.browser,
    headless: args.headless,
    args: report.launch.args,
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    locale: 'zh-CN',
  });
  page = await context.newPage();
  page.on('console', (message) => {
    if (message.type() === 'error') report.console_errors.push(message.text());
  });
  page.on('pageerror', (error) => report.page_errors.push(error.stack || error.message));

  const navigationStarted = performance.now();
  await page.goto(`${viewerBase}/?task=${encodeURIComponent(args.task)}#token=${encodeURIComponent(token)}`, {
    waitUntil: 'domcontentloaded',
    timeout: args.timeoutMs,
  });
  await page.waitForFunction(() => Boolean(window.__viewer?.viewer?.renderer && window.__viewer?.ui), null, {
    timeout: args.timeoutMs,
  });
  await page.waitForFunction(() => Boolean(window.__viewer?.state?.data), null, {
    timeout: args.timeoutMs,
  });
  report.timings.model_metadata_ms = performance.now() - navigationStarted;

  const geometryStarted = performance.now();
  await page.waitForFunction(
    () => Boolean(window.__viewer?.viewer?._lastVtuResult && !window.__viewer?.ui?._frameBusy),
    null,
    { timeout: args.timeoutMs },
  );
  report.timings.geometry_build_upload_ms = performance.now() - geometryStarted;
  report.timings.total_load_ms = performance.now() - navigationStarted;
  await page.waitForTimeout(250);

  const snapshot = await page.evaluate(() => {
    const app = window.__viewer;
    const { viewer, state } = app;
    const renderer = viewer.renderer;
    const gl = renderer.getContext();
    const debug = gl.getExtension('WEBGL_debug_renderer_info');
    const lineGroup = viewer._lineGroup;
    const lineSegments = lineGroup?.children?.[0] || null;
    return {
      data: {
        format: state.data?.format_version,
        nodes: state.data?.num_nodes,
        elements: state.data?.num_elements,
        frames: state.data?.frames?.length,
        fields: (state.data?.fields || []).map((field) => ({
          name: field.name,
          label: field.label,
          unit: field.unit,
          association: field.association,
        })),
      },
      vtu: viewer.getVtuStats(),
      build: viewer.lastTimings,
      scene: {
        mesh_children: viewer.meshGroup.children.length,
        line_children: lineGroup?.children?.length || 0,
        line_positions: lineSegments?.geometry?.attributes?.position?.count || 0,
        line_indices: lineSegments?.geometry?.index?.count || 0,
        frame_label: document.getElementById('frame-label')?.textContent || '',
        legend_hidden: document.getElementById('legend')?.classList.contains('hidden'),
      },
      webgl: {
        version: gl.getParameter(gl.VERSION),
        shading_language_version: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
        vendor: debug ? gl.getParameter(debug.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
        renderer: debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
        webgl2: typeof WebGL2RenderingContext !== 'undefined' && gl instanceof WebGL2RenderingContext,
        max_texture_size: gl.getParameter(gl.MAX_TEXTURE_SIZE),
      },
      memory: {
        geometries: renderer.info.memory.geometries,
        textures: renderer.info.memory.textures,
      },
      render: {
        calls: renderer.info.render.calls,
        triangles: renderer.info.render.triangles,
        lines: renderer.info.render.lines,
        points: renderer.info.render.points,
        frame: renderer.info.render.frame,
      },
      camera: viewer.camera.position.toArray(),
    };
  });

  assert.equal(snapshot.data.nodes, args.expectedNodes, 'viewer node count does not match benchmark');
  assert.equal(snapshot.data.elements, args.expectedElements, 'viewer element count does not match benchmark');
  assert.ok(snapshot.vtu.nodes >= args.expectedNodes, 'VTU geometry node count is too small');
  const hasLineGeometry = snapshot.scene.line_children > 0 && snapshot.scene.line_indices > 0;
  const hasSurfaceGeometry = snapshot.scene.mesh_children > 0;
  const expectedGeometryPresent = {
    line: hasLineGeometry,
    surface: hasSurfaceGeometry,
    any: hasLineGeometry || hasSurfaceGeometry,
  }[args.geometry];
  assert.equal(expectedGeometryPresent, true, `${args.geometry} geometry was not uploaded`);
  assert.equal(snapshot.webgl.webgl2, true, 'WebGL 2 is required');
  report.gpu = snapshot.webgl;
  const softwarePattern = /swiftshader|softwarerasterizer|llvmpipe|microsoft basic render|warp/i;
  assert.equal(
    softwarePattern.test(`${snapshot.webgl.vendor} ${snapshot.webgl.renderer}`),
    false,
    `A real GPU is required; browser selected software rendering: ${snapshot.webgl.renderer}`,
  );
  report.renderer = {
    memory: snapshot.memory,
    initial_render: snapshot.render,
    scene: snapshot.scene,
    data: snapshot.data,
    vtu: snapshot.vtu,
    build_timings: snapshot.build,
  };

  const screenshot = page.locator('#viewport > canvas').first();
  const buffer = await screenshot.screenshot();
  const digest = crypto.createHash('sha256').update(buffer).digest('hex');
  const pixels = await page.evaluate(async (base64) => {
    const image = new Image();
    image.src = 'data:image/png;base64,' + base64;
    await image.decode();
    const canvas = document.createElement('canvas');
    canvas.width = image.width;
    canvas.height = image.height;
    const context = canvas.getContext('2d', { willReadFrequently: true });
    context.drawImage(image, 0, 0);
    const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
    const colors = new Set();
    let sampled = 0;
    let nonBackground = 0;
    let luminanceMin = 255;
    let luminanceMax = 0;
    for (let i = 0; i < data.length; i += 32) {
      const r = data[i];
      const g = data[i + 1];
      const b = data[i + 2];
      const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
      luminanceMin = Math.min(luminanceMin, luminance);
      luminanceMax = Math.max(luminanceMax, luminance);
      colors.add(`${r >> 3},${g >> 3},${b >> 3}`);
      if (Math.abs(r - 13) + Math.abs(g - 17) + Math.abs(b - 23) > 18) nonBackground += 1;
      sampled += 1;
    }
    return {
      width: image.width,
      height: image.height,
      sampled,
      non_background: nonBackground,
      non_background_ratio: nonBackground / sampled,
      unique_coarse_colors: colors.size,
      luminance_min: luminanceMin,
      luminance_max: luminanceMax,
    };
  }, buffer.toString('base64'));
  assert.ok(pixels.width > 300 && pixels.height > 250, 'canvas dimensions are invalid');
  assert.ok(pixels.non_background_ratio > 0.0001, 'rendered canvas appears blank');
  assert.ok(pixels.unique_coarse_colors > 8, 'rendered canvas has too few colors');
  assert.ok(pixels.luminance_max - pixels.luminance_min > 20, 'rendered canvas has no visible contrast');
  report.pixels = { digest, ...pixels };

  const screenshotPath = path.join(outputDir, 'million-node-gpu.png');
  await page.screenshot({ path: screenshotPath, fullPage: true });
  report.screenshots.push(screenshotPath);

  const fps = await page.evaluate(async () => {
    const app = window.__viewer;
    const durations = [];
    const start = performance.now();
    let frames = 0;
    await new Promise((resolve) => {
      const frame = () => {
        const renderStarted = performance.now();
        app.viewer.renderer.render(app.viewer.scene, app.viewer.camera);
        durations.push(performance.now() - renderStarted);
        frames += 1;
        if (performance.now() - start < 3000) requestAnimationFrame(frame);
        else resolve();
      };
      requestAnimationFrame(frame);
    });
    const elapsedMs = performance.now() - start;
    durations.sort((a, b) => a - b);
    return {
      elapsed_ms: elapsedMs,
      frames,
      fps: frames / (elapsedMs / 1000),
      frame_time_ms_p50: durations[Math.floor((durations.length - 1) * 0.5)],
      frame_time_ms_p95: durations[Math.floor((durations.length - 1) * 0.95)],
      frame_time_ms_max: durations[durations.length - 1],
    };
  });
  report.renderer.forced_render_fps = fps;

  const beforeFrame = await page.evaluate(() => window.__viewer.viewer.renderer.info.render.frame);
  const beforeCamera = await page.evaluate(() => window.__viewer.viewer.camera.position.toArray());
  const interactionStarted = performance.now();
  const box = await page.locator('#viewport > canvas').first().boundingBox();
  assert.ok(box, 'canvas has no bounding box');
  const centerX = box.x + box.width * 0.5;
  const centerY = box.y + box.height * 0.5;
  await page.mouse.move(centerX, centerY);
  await page.mouse.down();
  await page.mouse.move(centerX + box.width * 0.12, centerY + box.height * 0.05, { steps: 8 });
  await page.mouse.up();
  await page.waitForFunction(
    (frame) => window.__viewer.viewer.renderer.info.render.frame > frame,
    beforeFrame,
    { timeout: 30000 },
  );
  const firstInteractionFrameMs = performance.now() - interactionStarted;
  await page.waitForTimeout(150);
  const afterCamera = await page.evaluate(() => window.__viewer.viewer.camera.position.toArray());
  const afterFrame = await page.evaluate(() => window.__viewer.viewer.renderer.info.render.frame);
  assert.notDeepEqual(afterCamera, beforeCamera, 'orbit interaction did not move the camera');
  assert.ok(afterFrame > beforeFrame, 'orbit interaction did not render a new frame');
  report.interaction = {
    first_rendered_frame_ms: firstInteractionFrameMs,
    frames_rendered: afterFrame - beforeFrame,
    camera_before: beforeCamera,
    camera_after: afterCamera,
  };

  const reportPath = path.join(outputDir, 'report.json');
  report.finished_at = new Date().toISOString();
  report.status = 'passed';
  await fs.writeFile(reportPath, JSON.stringify(report, null, 2), 'utf8');
  console.log(JSON.stringify({
    status: report.status,
    report: reportPath,
    nodes: snapshot.data.nodes,
    elements: snapshot.data.elements,
    renderer: snapshot.webgl.renderer,
    total_load_ms: report.timings.total_load_ms,
    forced_fps: fps.fps,
    first_rendered_frame_ms: firstInteractionFrameMs,
    non_background_ratio: pixels.non_background_ratio,
  }, null, 2));
} catch (error) {
  report.finished_at = new Date().toISOString();
  report.status = 'failed';
  report.error = error.stack || error.message;
  if (page) {
    try {
      const failurePath = path.join(outputDir, 'million-node-gpu-failure.png');
      await page.screenshot({ path: failurePath, fullPage: true });
      report.screenshots.push(failurePath);
    } catch {
      // Preserve the original failure if the page is already gone.
    }
  }
  const reportPath = path.join(outputDir, 'report.json');
  await fs.writeFile(reportPath, JSON.stringify(report, null, 2), 'utf8');
  console.error(JSON.stringify({
    status: report.status,
    report: reportPath,
    error: report.error,
    gpu_renderer: report.gpu.renderer || null,
  }, null, 2));
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
}
