import * as THREE from 'three';
import {COLORMAPS, sampleColormap} from './colormaps.js';

// Interpolate the scalar in the triangle, then map to a color per fragment.
// Interpolating RGB endpoints instead can skip the middle of the legend entirely.
export function contourCoordinates(values, count, min, max) {
  const result = new Float32Array(count * 2);
  for (let i = 0; i < count; i++) {
    const value = values?.[i];
    result[i * 2] = Number.isFinite(value) ? (max > min ? (value - min) / (max - min) : .5) : 0;
    result[i * 2 + 1] = Number.isFinite(value) ? 1 : 0;
  }
  return result;
}

export function createContourMaterial() {
  const material = new THREE.MeshBasicMaterial({side:THREE.DoubleSide, toneMapped:false,
    polygonOffset:true, polygonOffsetFactor:1, polygonOffsetUnits:1});
  material.userData.contour = {
    enabled:{value:0}, bands:{value:12}, stopCount:{value:2},
    stops:{value:Array.from({length:16},()=>new THREE.Vector3())},
  };
  material.onBeforeCompile = shader => {
    const u = material.userData.contour;
    Object.assign(shader.uniforms, {contourEnabled:u.enabled, contourBands:u.bands,
      contourStopCount:u.stopCount, contourStops:u.stops});
    shader.vertexShader = 'attribute vec2 contour; varying vec2 vContour;\n' + shader.vertexShader;
    shader.vertexShader = shader.vertexShader.replace('#include <begin_vertex>',
      '#include <begin_vertex>\nvContour = contour;');
    shader.fragmentShader = `varying vec2 vContour;
      uniform float contourEnabled, contourBands, contourStopCount;
      uniform vec3 contourStops[16];
      vec3 contourLinear(vec3 c) {
        return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045),c));
      }\n` + shader.fragmentShader;
    shader.fragmentShader = shader.fragmentShader.replace('#include <color_fragment>', `
      #include <color_fragment>
      if (contourEnabled > 0.5) {
        float t = clamp(vContour.x, 0.0, 1.0);
        if (contourBands > 1.0) t = (min(floor(t * contourBands), contourBands - 1.0) + 0.5) / contourBands;
        float index = t * (contourStopCount - 1.0);
        vec3 color = contourStops[0];
        for (int i = 0; i < 15; i++) {
          if (float(i) <= index && float(i) < contourStopCount - 1.0)
            color = mix(contourStops[i], contourStops[i+1], clamp(index - float(i),0.0,1.0));
        }
        if (vContour.y < 0.9999) color = vec3(0.55);
        diffuseColor.rgb = contourLinear(color);
      }
    `);
  };
  material.customProgramCacheKey = () => 'scalar-contour-v1';
  return material;
}

export function configureContour(material, enabled, name, bands) {
  const u = material.userData.contour;
  const colors = (COLORMAPS[name] || COLORMAPS.jet).colors;
  u.enabled.value = enabled ? 1 : 0;
  u.bands.value = bands;
  u.stopCount.value = colors.length;
  colors.forEach((color,i)=>u.stops.value[i].set(...color));
  material.color.set(enabled ? 0xffffff : 0x9aafc3);
}

export function bandedColormapCSS(name, bands = 0) {
  if (!bands) return null;
  const stops = [];
  for (let i=0;i<bands;i++) {
    const color = sampleColormap(name,(i+.5)/bands).map(v=>Math.round(v*255)).join(',');
    stops.push(`rgb(${color}) ${100*i/bands}%`, `rgb(${color}) ${100*(i+1)/bands}%`);
  }
  return `linear-gradient(to right, ${stops.join(',')})`;
}

// Node-index adjacency preserves separate parts even where coordinates coincide.
export function featureEdges(positions, indices, angle = 25) {
  const edges = new Map(), threshold = Math.cos(angle*Math.PI/180);
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  for (let i=0;i<indices.length;i+=3) {
    const nodes = [indices[i],indices[i+1],indices[i+2]];
    a.fromArray(positions,nodes[0]*3); b.fromArray(positions,nodes[1]*3); c.fromArray(positions,nodes[2]*3);
    const normal = b.sub(a).cross(c.sub(a)).normalize();
    for(let j=0;j<3;j++) {
      const x=nodes[j], y=nodes[(j+1)%3], key=x<y?`${x},${y}`:`${y},${x}`;
      const edge=edges.get(key);
      if(edge) {edge.count++; if(Math.abs(edge.normal.dot(normal)) < threshold) edge.crease=true;}
      else edges.set(key,{x,y,count:1,normal:normal.clone(),crease:false});
    }
  }
  const result=[];
  for(const edge of edges.values()) if(edge.count!==2 || edge.crease) result.push(edge.x,edge.y);
  return new Uint32Array(result);
}
