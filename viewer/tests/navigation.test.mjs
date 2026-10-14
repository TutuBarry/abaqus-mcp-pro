import {test} from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {TrackballControls} from 'three/examples/jsm/controls/TrackballControls.js';
import {sampleControlInputs} from '../src/gestures.js';
import {UIController} from '../src/ui.js';

function globals(t, values) {
  for (const [name,value] of Object.entries(values)) {
    const previous = Object.getOwnPropertyDescriptor(globalThis,name);
    Object.defineProperty(globalThis,name,{value,configurable:true});
    t.after(() => previous ? Object.defineProperty(globalThis,name,previous) : delete globalThis[name]);
  }
}

// Minimal DOM event phases, using the real Three.js control implementation.
function canvas() {
  const handlers = new Map();
  return {
    style:{}, ownerDocument:{documentElement:{clientLeft:0,clientTop:0}},
    getBoundingClientRect:() => ({left:0,top:0,width:1000,height:600}),
    setPointerCapture() {}, releasePointerCapture() {},
    addEventListener(name,fn,options) {
      const list = handlers.get(name) || [];
      list.push({fn,capture:options === true || !!options?.capture}); handlers.set(name,list);
    },
    removeEventListener(name,fn) {handlers.set(name,(handlers.get(name) || []).filter(h=>h.fn!==fn));},
    send(name,props) {
      const event = {pointerType:'mouse',pointerId:1,button:0,preventDefault() {},...props};
      for (const {fn} of [...(handlers.get(name) || [])].sort((a,b)=>Number(b.capture)-Number(a.capture))) fn(event);
    },
  };
}

test('same drag distance produces the same rotation at sparse and dense pointer rates', t => {
  globals(t,{window:Object.assign(new EventTarget(),{pageXOffset:0,pageYOffset:0})});
  const drag = (count, sampled) => {
    const dom=canvas(), camera=new THREE.PerspectiveCamera(); camera.position.z=10;
    const control=new TrackballControls(camera,dom); control.staticMoving=true; control.rotateSpeed=6;
    const unbind=sampled ? sampleControlInputs(dom,control) : () => {};
    dom.send('pointerdown',{pageX:500,pageY:300});
    for (let i=1;i<=count;i++) dom.send('pointermove',{pageX:500+40*i/count,pageY:300});
    dom.send('pointerup',{pageX:540,pageY:300}); control.update();
    const q=camera.quaternion.clone(); unbind(); control.dispose(); return q;
  };
  const reference=drag(1,true), dense=drag(40,true), oldDense=drag(40,false);
  assert.ok(reference.angleTo(dense)<1e-7);
  assert.ok(reference.angleTo(oldDense)>.4); // Reproduces the dropped-input defect.
});

test('wheel bursts retain every zoom sample without waiting for a render frame', t => {
  globals(t,{window:Object.assign(new EventTarget(),{pageXOffset:0,pageYOffset:0})});
  const zoom = updateEveryEvent => {
    const dom=canvas(),camera=new THREE.PerspectiveCamera(); camera.position.z=10;
    const control=new TrackballControls(camera,dom); control.staticMoving=true; control.zoomSpeed=6;
    const unbind=sampleControlInputs(dom,control);
    for (let i=0;i<8;i++) {dom.send('wheel',{deltaMode:0,deltaY:-120}); if(updateEveryEvent) control.update();}
    control.update(); const distance=camera.position.length(); unbind(); control.dispose(); return distance;
  };
  assert.ok(Math.abs(zoom(false)-zoom(true))<1e-10);
  assert.ok(zoom(false)<10);
});

test('sensitivity changes apply live and survive rebinding; invalid saved values are ignored', t => {
  const elements=new Map();
  for (const [name,max] of [['rotate',20],['zoom',10]]) {
    elements.set(name+'-sensitivity',Object.assign(new EventTarget(),{min:'0.5',max:String(max),value:'6'}));
    elements.set(name+'-sensitivity-val',{textContent:''});
  }
  let stored='{"rotateSpeed":-1,"zoomSpeed":999}';
  globals(t,{document:{getElementById:id=>elements.get(id)},
    localStorage:{getItem:()=>stored,setItem:(_key,value)=>{stored=value;}}});
  const controls={rotateSpeed:6,zoomSpeed:6};
  UIController.prototype._bindNavigationSensitivity.call({viewer:{controls}});
  assert.deepEqual(controls,{rotateSpeed:6,zoomSpeed:6});
  const slider=elements.get('rotate-sensitivity'); slider.value='9.5'; slider.dispatchEvent(new Event('input'));
  assert.equal(controls.rotateSpeed,9.5);
  assert.equal(elements.get('rotate-sensitivity-val').textContent,'9.5');
  const reloaded={rotateSpeed:6,zoomSpeed:6};
  UIController.prototype._bindNavigationSensitivity.call({viewer:{controls:reloaded}});
  assert.equal(reloaded.rotateSpeed,9.5);
});
