// Color map definitions — each is a list of [r,g,b] stops
export const COLORMAPS = {
  jet: [
    [0,0,0.56],[0,0,1],[0,0.5,1],[0,1,1],
    [0,1,0.5],[0.5,1,0],[1,1,0],[1,0.5,0],[1,0,0],[0.5,0,0]
  ],
  coolwarm: [
    [0.23,0.30,0.75],[0.40,0.52,0.90],[0.56,0.70,0.96],
    [0.75,0.86,0.99],[0.93,0.96,1.00],[0.99,0.93,0.88],
    [0.98,0.78,0.63],[0.94,0.57,0.39],[0.82,0.33,0.19],[0.65,0.06,0.06]
  ],
  rainbow: [
    [0.98,0.01,0.00],[0.99,0.48,0.00],[0.99,0.98,0.00],
    [0.00,0.90,0.07],[0.00,0.60,0.80],[0.20,0.00,0.60]
  ],
  greyscale: [
    [0,0,0],[0.11,0.11,0.11],[0.22,0.22,0.22],[0.33,0.33,0.33],
    [0.44,0.44,0.44],[0.56,0.56,0.56],[0.67,0.67,0.67],
    [0.78,0.78,0.78],[0.89,0.89,0.89],[1,1,1]
  ],
  inferno: [
    [0.00,0.00,0.02],[0.11,0.06,0.33],[0.32,0.09,0.47],
    [0.53,0.13,0.46],[0.72,0.22,0.33],[0.86,0.38,0.16],
    [0.94,0.58,0.02],[0.97,0.78,0.13],[0.99,0.96,0.59]
  ],
  viridis: [
    [0.27,0.00,0.33],[0.28,0.24,0.42],[0.24,0.45,0.47],
    [0.18,0.64,0.43],[0.21,0.81,0.28],[0.49,0.92,0.11],
    [0.75,0.96,0.09],[0.94,0.98,0.13],[0.99,0.99,0.71]
  ],
};

/** Sample a color map at t in [0,1], returning [r,g,b] */
export function sampleColormap(name, t) {
  const stops = COLORMAPS[name] || COLORMAPS.jet;
  t = Math.max(0, Math.min(1, t));
  const idx = t * (stops.length - 1);
  const lo = Math.floor(idx);
  const hi = Math.min(lo + 1, stops.length - 1);
  const f = idx - lo;
  return [
    stops[lo][0] + (stops[hi][0] - stops[lo][0]) * f,
    stops[lo][1] + (stops[hi][1] - stops[lo][1]) * f,
    stops[lo][2] + (stops[hi][2] - stops[lo][2]) * f,
  ];
}

/** Return a CSS gradient string for a color map */
export function colormapCSSGradient(name) {
  const stops = COLORMAPS[name] || COLORMAPS.jet;
  return 'linear-gradient(to right, ' +
    stops.map((c, i) => {
      const pct = (i / (stops.length - 1)) * 100;
      return `rgb(${Math.round(c[0]*255)},${Math.round(c[1]*255)},${Math.round(c[2]*255)}) ${pct}%`;
    }).join(', ') +
  ')';
}

/** Draw a color map onto a 2D canvas */
export function drawColormapOnCanvas(canvas, name, width, height) {
  const ctx = canvas.getContext('2d');
  const stops = COLORMAPS[name] || COLORMAPS.jet;
  const imageData = ctx.createImageData(width, height);
  for (let x = 0; x < width; x++) {
    const t = x / (width - 1);
    const [r, g, b] = sampleColormap(name, t);
    for (let y = 0; y < height; y++) {
      const idx = (y * width + x) * 4;
      imageData.data[idx] = Math.round(r * 255);
      imageData.data[idx + 1] = Math.round(g * 255);
      imageData.data[idx + 2] = Math.round(b * 255);
      imageData.data[idx + 3] = 255;
    }
  }
  ctx.putImageData(imageData, 0, 0);
}

/** Format a number for display */
export function fmtNum(v) {
  if (v === undefined || v === null) return '-';
  if (Math.abs(v) < 0.001 || Math.abs(v) > 1e6) return v.toExponential(2);
  return parseFloat(v.toPrecision(4)).toString();
}
