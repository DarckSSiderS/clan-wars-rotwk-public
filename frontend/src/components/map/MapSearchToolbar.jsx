import React from 'react';

const MapSearchToolbar = ({
  searchValue,
  territories,
  strongholds,
  regionValue,
  getTerritoryLabel,
  labels,
  onSearchChange,
  onSearchSubmit,
  onRegionChange,
}) => (
  <section className="card map-toolbar" aria-label={labels.controls}>
    <div className="map-toolbar__search">
      <input
        className="input"
        list="map-territory-options"
        value={searchValue}
        onChange={(event) => onSearchChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') onSearchSubmit();
        }}
        placeholder={labels.searchPlaceholder}
        aria-label={labels.searchPlaceholder}
      />
      <datalist id="map-territory-options">
        {territories.map((territory) => (
          <option key={territory.id} value={getTerritoryLabel(territory)} />
        ))}
      </datalist>
      <select
        className="input map-region-select"
        aria-label={labels.strongholds}
        value={regionValue}
        onChange={(event) => onRegionChange(event.target.value)}
      >
        <option value="all">{labels.strongholds}</option>
        {strongholds.map((territory) => (
          <option value={territory.id} key={territory.id}>
            {getTerritoryLabel(territory)}
          </option>
        ))}
      </select>
    </div>
  </section>
);

export default MapSearchToolbar;
