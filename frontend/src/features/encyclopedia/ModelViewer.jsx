import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { clone } from 'three/addons/utils/SkeletonUtils.js';
import { useLocalizationContext } from '../../contexts/LocalizationContext';
import { matchesMesh, meshVisible } from './modelRules';
import { encyclopediaAssetFetch } from '../../services/apiFetch';

function disposeTree(root) {
  const geometries = new Set();
  const materials = new Set();
  const textures = new Set();
  root?.traverse((object) => {
    if (object.geometry) geometries.add(object.geometry);
    for (const material of [object.material].flat().filter(Boolean)) {
      materials.add(material);
      Object.values(material).forEach((value) => { if (value?.isTexture) textures.add(value); });
    }
  });
  geometries.forEach((value) => value.dispose());
  materials.forEach((value) => value.dispose());
  textures.forEach((value) => { value.source?.data?.close?.(); value.dispose(); });
}

function ModelScene({ profile, variant, weapon, formation }) {
  const { getLocalizedText: t } = useLocalizationContext();
  const host = useRef(null);
  const runtime = useRef(null);
  const [status, setStatus] = useState('loading');
  const [actions, setActions] = useState([]);
  const [action, setAction] = useState('idle');
  const [playing, setPlaying] = useState(() => !window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const container = host.current;
    const abort = new AbortController();
    let active = true;
    let renderer;
    let observer;
    let frame;
    let scene;
    let controls;
    let model;
    let elapsed = 0;
    let previous = 0;
    const mixers = [];
    const contextLost = (event) => { event.preventDefault(); if (active) setStatus('error'); };
    async function init() {
      try {
        renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.25;
        renderer.domElement.addEventListener('webglcontextlost', contextLost);
        container.appendChild(renderer.domElement);
        scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 200);
        controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.enablePan = false;
        controls.minDistance = 2;
        controls.maxDistance = 50;
        controls.maxPolarAngle = Math.PI * 0.52;
        scene.add(new THREE.HemisphereLight(0xe7e8df, 0x34342b, 2.5));
        const light = new THREE.DirectionalLight(0xffe6bd, 4.5);
        light.position.set(6, 9, 5);
        scene.add(light);
        const rim = new THREE.DirectionalLight(0x98c3e2, 3);
        rim.position.set(-6, 5, -5);
        scene.add(rim);
        const platform = new THREE.Mesh(new THREE.CylinderGeometry(3.2, 3.4, 0.12, 80), new THREE.MeshStandardMaterial({ color: 0x23271e, roughness: 0.9 }));
        platform.position.y = -0.1;
        scene.add(platform);
        const ring = new THREE.Mesh(new THREE.RingGeometry(3.12, 3.16, 80), new THREE.MeshBasicMaterial({ color: 0xbda56d, side: THREE.DoubleSide }));
        ring.rotation.x = -Math.PI / 2;
        scene.add(ring);
        const response = await encyclopediaAssetFetch(weapon?.model || variant.model, { signal: abort.signal });
        if (!response.ok) throw new Error(`Model HTTP ${response.status}`);
        const gltf = await new GLTFLoader().parseAsync(await response.arrayBuffer(), '');
        if (!active) { disposeTree(gltf.scene); return; }
        model = gltf.scene;
        model.traverse((object) => {
          if (!object.isMesh) return;
          const name = object.name.toUpperCase();
          object.frustumCulled = false;
          object.visible = meshVisible(name, variant, weapon, 'idle');
          for (const material of [object.material].flat()) {
            material.transparent = false;
            material.opacity = 1;
            material.alphaTest = variant.alphaTest ?? 0.5;
            material.side = THREE.DoubleSide;
            material.depthWrite = true;
            if ('roughness' in material) material.roughness = Math.max(material.roughness, 0.68);
            if (matchesMesh(name, variant.additiveMeshes, variant.additivePrefixes)) {
              material.transparent = true;
              material.alphaMap = material.map;
              material.depthWrite = false;
              material.alphaTest = 0.08;
              material.color?.set(0xffffff);
            }
            if ((variant.metalMeshes || []).includes(name)) {
              material.color?.set(0x70777b);
              material.metalness = 0.78;
              material.roughness = 0.3;
            }
          }
        });
        model.updateMatrixWorld(true);
        const box = new THREE.Box3();
        model.traverse((object) => {
          if (object.isMesh && object.visible) box.union(new THREE.Box3().setFromObject(object, true));
        });
        const size = box.getSize(new THREE.Vector3());
        const center = box.getCenter(new THREE.Vector3());
        const scale = (variant.targetHeight || 4.85) / Math.max(size.y, size.x * 0.6, size.z * 0.6, 0.001);
        model.scale.setScalar(scale);
        model.position.set(-center.x * scale, -box.min.y * scale, -center.z * scale);
        const group = new THREE.Group();
        group.add(model);
        if (formation) {
          const config = profile.formation || { count: 9, columns: 3, gapX: 1.5, gapZ: 1.6, scale: 0.72 };
          model.scale.multiplyScalar(config.scale);
          model.position.multiplyScalar(config.scale);
          for (let index = 1; index < config.count; index += 1) group.add(clone(model));
          group.children.forEach((member, index) => {
            member.position.x += (index % config.columns - (config.columns - 1) / 2) * config.gapX;
            member.position.z += (Math.floor(index / config.columns) - (Math.ceil(config.count / config.columns) - 1) / 2) * config.gapZ;
          });
          platform.scale.set(2, 1, 2);
          ring.scale.setScalar(2);
        }
        scene.add(group);
        group.children.forEach((member) => mixers.push(new THREE.AnimationMixer(member)));
        const clips = { ...variant.clips, ...weapon?.clips };
        const supported = Object.entries(clips).filter(([, name]) => gltf.animations.some((clip) => clip.name.toUpperCase() === name.toUpperCase()));
        const home = () => {
          const distance = formation ? 21 : 12.5;
          camera.position.set(distance * 0.86, formation ? 9 : 3.5, -distance * 0.35);
          controls.target.set(0, formation ? 1 : size.y * scale / 2, 0);
          controls.update();
        };
        runtime.current = { group, mixers, animations: gltf.animations, clips, home };
        home();
        setActions(supported.map(([key]) => key));
        setAction(supported.some(([key]) => key === 'idle') ? 'idle' : supported[0]?.[0] || '');
        const resize = () => {
          const width = container.clientWidth;
          const height = container.clientHeight;
          if (!width || !height) return;
          renderer.setSize(width, height);
          camera.aspect = width / height;
          camera.updateProjectionMatrix();
        };
        observer = new ResizeObserver(resize);
        observer.observe(container);
        resize();
        const render = (now) => {
          if (!active) return;
          const delta = Math.min((now - (previous || now)) / 1000, 0.05);
          previous = now;
          if (!document.hidden) {
            mixers.forEach((mixer) => mixer.update(delta));
            elapsed += delta * (mixers[0]?.timeScale || 0);
            container.dataset.animationTime = elapsed.toFixed(3);
            controls.update();
            renderer.render(scene, camera);
            container.dataset.drawCalls = String(renderer.info.render.calls);
          }
          frame = requestAnimationFrame(render);
        };
        frame = requestAnimationFrame(render);
        setStatus('ready');
      } catch (error) {
        if (active && error.name !== 'AbortError') setStatus('error');
      }
    }
    init();
    return () => {
      active = false;
      abort.abort();
      cancelAnimationFrame(frame);
      observer?.disconnect();
      controls?.dispose();
      mixers.forEach((mixer) => { mixer.stopAllAction(); mixer.uncacheRoot(mixer.getRoot()); });
      disposeTree(scene);
      renderer?.domElement.removeEventListener('webglcontextlost', contextLost);
      renderer?.dispose();
      renderer?.forceContextLoss();
      renderer?.domElement.remove();
      runtime.current = null;
    };
  }, [profile, variant, weapon, formation, attempt]);

  useEffect(() => {
    const value = runtime.current;
    if (!value || status !== 'ready') return;
    value.group.traverse((object) => {
      if (object.isMesh) object.visible = meshVisible(object.name.toUpperCase(), variant, weapon, action);
    });
    const clip = value.animations.find((item) => item.name.toUpperCase() === value.clips[action]?.toUpperCase());
    value.mixers.forEach((mixer) => {
      mixer.stopAllAction();
      if (clip) mixer.clipAction(clip).reset().play();
    });
  }, [action, status, variant, weapon]);

  useEffect(() => {
    runtime.current?.mixers.forEach((mixer) => { mixer.timeScale = playing ? 1 : 0; });
  }, [playing, status]);

  return <>
    <div className="encyclopedia-stage" data-testid="model-stage" data-status={status}>
      <div className="encyclopedia-canvas" ref={host} role="img" aria-label={t('archive_model')} />
      {status !== 'ready' && <div className="encyclopedia-stage-message" role={status === 'error' ? 'alert' : 'status'}>
        <p>{t(status === 'error' ? 'archive_model_error' : 'archive_model_loading')}</p>
        {status === 'error' && <button type="button" onClick={() => { setStatus('loading'); setAttempt((value) => value + 1); }}>{t('archive_retry')}</button>}
      </div>}
      {status === 'ready' && <span className="encyclopedia-orbit-hint">{t('archive_orbit_hint')}</span>}
    </div>
    <div className="encyclopedia-playback">
      <label>{t('archive_animation')}<select aria-label={t('archive_animation')} value={action} disabled={status !== 'ready' || !actions.length} onChange={(event) => setAction(event.target.value)}>
        {!actions.length && <option value="">{t('archive_static')}</option>}
        {actions.map((key) => <option key={key} value={key}>{t(`archive_action_${key}`, key)}</option>)}
      </select></label>
      <button type="button" disabled={status !== 'ready' || !actions.length} onClick={() => setPlaying((value) => !value)}>{t(playing ? 'archive_pause' : 'archive_play')}</button>
      <button type="button" disabled={status !== 'ready'} onClick={() => runtime.current?.home()}>{t('archive_reset_camera')}</button>
    </div>
  </>;
}

export default function ModelViewer({ profile, variant, weapon, formation }) {
  return <ModelScene key={`${profile.id}/${variant.id}/${weapon?.id || ''}/${formation}`} {...{ profile, variant, weapon, formation }} />;
}
