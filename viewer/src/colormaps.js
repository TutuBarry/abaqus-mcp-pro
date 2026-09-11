/**
 * Colormap definitions.
 * Each colormap is an array of [r,g,b] stops in [0,1] range.
 */

export const COLORMAPS = {
  jet: {
    name: 'Jet',
    colors: [
      [0, 0, 0.56], [0, 0, 1], [0, 0.5, 1], [0, 1, 1],
      [0, 1, 0.5], [0.5, 1, 0], [1, 1, 0], [1, 0.5, 0],
      [1, 0, 0], [0.5, 0, 0],
    ],
  },
  coolwarm: {
    name: 'Cool-Warm',
    colors: [
      [0.23, 0.30, 0.75], [0.35, 0.42, 0.83], [0.50, 0.55, 0.90],
      [0.65, 0.68, 0.93], [0.80, 0.80, 0.85], [0.90, 0.75, 0.65],
      [0.95, 0.60, 0.45], [0.90, 0.42, 0.28], [0.80, 0.25, 0.15],
    ],
  },
  rainbow: {
    name: 'Rainbow',
    colors: [
      [0.28, 0, 0.53], [0, 0, 0.75], [0, 0.38, 0.75],
      [0, 0.63, 0.40], [0.20, 0.80, 0.20], [0.60, 0.78, 0],
      [0.85, 0.65, 0], [0.95, 0.35, 0], [0.85, 0, 0],
    ],
  },
  greyscale: {
    name: 'Greyscale',
    colors: [
      [0, 0, 0], [0.125, 0.125, 0.125], [0.25, 0.25, 0.25],
      [0.375, 0.375, 0.375], [0.5, 0.5, 0.5],
      [0.625, 0.625, 0.625], [0.75, 0.75, 0.75],
      [0.875, 0.875, 0.875], [1, 1, 1],
    ],
  },
  inferno: {
    name: 'Inferno',
    colors: [
      [0, 0, 0.02], [0.04, 0.02, 0.22], [0.15, 0.02, 0.45],
      [0.34, 0.02, 0.52], [0.55, 0.08, 0.42], [0.75, 0.22, 0.22],
      [0.90, 0.42, 0.07], [0.97, 0.65, 0.03], [1, 0.90, 0.10],
    ],
  },
  viridis: {
    name: 'Viridis',
    colors: [
      [0.27, 0.00, 0.33], [0.28, 0.16, 0.42], [0.26, 0.30, 0.51],
      [0.20, 0.45, 0.54], [0.13, 0.58, 0.51], [0.13, 0.71, 0.42],
      [0.35, 0.82, 0.28], [0.64, 0.89, 0.14], [0.99, 0.96, 0.00],
    ],
  },
};

/**
 * Interpolate a colormap at position t in [0, 1].
 * @param {string} name - colormap key
 * @param {number} t - normalized value 0..1
 * @returns {[number, number, number]} [r, g, b] each in [0,1]
 */
export function sampleColormap(name, t) {
  const cmap = COLORMAPS[name] || COLORMAPS.jet;
  const stops = cmap.colors;
  const n = stops.length;
  t = Math.max(0, Math.min(1, t));
  const idx = t * (n - 1);
  const lo = Math.floor(idx);
  const hi = Math.min(lo + 1, n - 1);
  const f = idx - lo;
  return [
    stops[lo][0] + (stops[hi][0] - stops[lo][0]) * f,
    stops[lo][1] + (stops[hi][1] - stops[lo][1]) * f,
    stops[lo][2] + (stops[hi][2] - stops[lo][2]) * f,
  ];
}

/**
 * Generate a CSS gradient string for a colormap.
 */
export function colormapToCSS(name) {
  const cmap = COLORMAPS[name] || COLORMAPS.jet;
  const stops = cmap.colors.map((c, i) => {
    const pct = (i / (cmap.colors.length - 1)) * 100;
    return `${pct}% rgb(${Math.round(c[0]*255)},${Math.round(c[1]*255)},${Math.round(c[2]*255)})`;
  });
  return `linear-gradient(to right, ${stops.join(',')})`;
}

/**
 * Get a list of available colormap names.
 */
export function getColormapNames() {
  return Object.keys(COLORMAPS);
}
