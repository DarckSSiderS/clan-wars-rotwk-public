import React, { useEffect, useRef, useState } from 'react';
import { ArrowForward, Shield } from '@mui/icons-material';
import { Link } from 'react-router-dom';
import { publicFetch } from '../../services/apiFetch';

const normalizePathData = (value) => String(value || '').replace(/\s+/g, ' ').trim();

const TacticalMapPreview = ({
  activeWars = [],
  label,
  errorLabel,
  markerLabel,
  openLabel,
}) => {
  const hostRef = useRef(null);
  const [svgContent, setSvgContent] = useState('');
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;

    publicFetch('/map-interactive.svg')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.text();
      })
      .then((content) => {
        if (!active) return;
        setSvgContent(content);
        setFailed(false);
      })
      .catch((error) => {
        if (!active || error.name === 'AbortError') return;
        setFailed(true);
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !svgContent) return undefined;

    host.innerHTML = svgContent;
    const svg = host.querySelector('svg');
    if (!svg) {
      setFailed(true);
      return undefined;
    }

    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    const pathIndex = new Map(
      [...svg.querySelectorAll('path.interactive-region')]
        .map((path) => [normalizePathData(path.getAttribute('d')), path]),
    );
    const layer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    layer.setAttribute('class', 'home-war-markers');

    activeWars.forEach((war) => {
      const path = pathIndex.get(normalizePathData(war.territory_svg_path_data));
      if (!path) return;
      const box = path.getBBox();
      const marker = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      marker.setAttribute('class', 'home-war-marker');
      marker.setAttribute(
        'transform',
        `translate(${box.x + box.width / 2} ${box.y + box.height / 2})`,
      );

      const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      title.textContent = war.territory_name;
      marker.appendChild(title);

      for (const [className, radius] of [
        ['home-war-marker__pulse home-war-marker__pulse--inner', '64'],
        ['home-war-marker__pulse home-war-marker__pulse--outer', '92'],
        ['home-war-marker__core', '36'],
      ]) {
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('class', className);
        circle.setAttribute('r', radius);
        marker.appendChild(circle);
      }

      layer.appendChild(marker);
    });

    svg.appendChild(layer);
    return () => {
      layer.remove();
      host.replaceChildren();
    };
  }, [activeWars, svgContent]);

  if (failed) {
    return (
      <div className="home-map-preview home-map-preview--failed" role="status">
        <p>{errorLabel}</p>
      </div>
    );
  }

  return (
    <Link to="/map" className="home-map-preview" aria-label={`${label}. ${openLabel}`}>
      <div className="home-map-preview__canvas" data-testid="home-tactical-map">
        {!svgContent && <div className="home-page__skeleton home-page__skeleton--map-inner" aria-hidden="true" />}
        <div ref={hostRef} className="home-map-preview__svg" role="img" aria-label={label} />
        <span className="home-map-preview__war-count">
          <Shield aria-hidden="true" />
          {markerLabel}
        </span>
      </div>
      <span className="home-map-preview__footer">
        <span>{openLabel}</span>
        <ArrowForward aria-hidden="true" />
      </span>
    </Link>
  );
};

export default TacticalMapPreview;
