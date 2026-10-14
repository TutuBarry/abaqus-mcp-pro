// TrackballControls overwrites its pending rotation delta on each pointermove.
// Consume the preceding sample before its handler runs, even between RAF ticks.
// Wheel samples are consumed individually too, avoiding large batched zoom jumps.
export function sampleControlInputs(canvas, controls) {
  const update = () => { if (controls.enabled) controls.update(); };
  const options = {capture:true, passive:true};
  for (const name of ['pointermove', 'wheel']) canvas.addEventListener(name, update, options);
  return () => {
    for (const name of ['pointermove', 'wheel']) canvas.removeEventListener(name, update, options);
  };
}

// A completed orbit/pan is not a probe or measurement click.
export function guardDragClicks(canvas) {
  let origin = null, dragged = false;
  const down = e => {
    dragged = origin !== null;
    origin = {x:e.clientX, y:e.clientY};
  };
  const move = e => {
    if (origin && Math.hypot(e.clientX - origin.x, e.clientY - origin.y) > 5) dragged = true;
  };
  const up = e => { move(e); origin = null; };
  const cancel = () => { origin = null; dragged = true; };
  const click = e => {
    if (dragged) { e.preventDefault(); e.stopImmediatePropagation(); }
    dragged = false;
  };
  const handlers = {pointerdown:down, pointermove:move, pointerup:up, pointercancel:cancel, click};
  const options = {capture:true};
  for (const [name, handler] of Object.entries(handlers)) canvas.addEventListener(name, handler, options);
  return () => {
    for (const [name, handler] of Object.entries(handlers)) canvas.removeEventListener(name, handler, options);
  };
}
