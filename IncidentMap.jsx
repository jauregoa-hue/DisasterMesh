import React, {useEffect, useState} from 'react';
import {CircleMarker, MapContainer, Popup, TileLayer, useMap} from 'react-leaflet';
import 'leaflet/dist/leaflet.css';

const labels = {missing: 'No GPS fix received', stale: 'GPS fix is stale', future: 'GPS clock is in the future',
  unknown_time: 'GPS fix has no trusted timestamp', invalid: 'Invalid GPS fix', valid: 'GPS valid at SOS time'};
export function locationLabel(gateway) {
  return gateway ? (labels[gateway.gps_status] || 'Location unavailable') : 'Location not provided';
}

function FitLocations({points}) {
  const map = useMap();
  const coordinates = JSON.stringify(points.map(i => [i.gateway.latitude, i.gateway.longitude]));
  useEffect(() => {
    const locations = JSON.parse(coordinates);
    if (locations.length) map.fitBounds(locations, {padding: [35, 35], maxZoom: 15});
  }, [map, coordinates]);
  return null;
}

export default function IncidentMap({items}) {
  const [tileError, setTileError] = useState(false);
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    return () => {window.removeEventListener('online', update); window.removeEventListener('offline', update)};
  }, []);
  const points = items.filter(i => i.gateway?.gps_status === 'valid' &&
    Number.isFinite(i.gateway.latitude) && Number.isFinite(i.gateway.longitude));
  const tileUrl = import.meta.env.VITE_MAP_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
  if (!points.length) return <section className="panel"><h2>Emergency locations</h2><p>No valid GPS locations to map. Reports remain available below.</p></section>;
  return <section className="panel"><h2>Emergency locations</h2>
    <p className="muted">Locations show the GPS fix known at SOS time. They do not track a person's current location.</p>
    {(tileError || !online) && <p className="notice" role="status">Map tiles unavailable or offline. Markers and exact coordinates remain available; the background may be blank.
      <button className="secondary" onClick={() => setTileError(false)}>Retry tiles</button></p>}
    <MapContainer center={[points[0].gateway.latitude, points[0].gateway.longitude]} zoom={13} className="incident-map" aria-label="Emergency incident map">
      <TileLayer key={String(tileError)} url={tileUrl} attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        eventHandlers={{tileerror: () => setTileError(true)}}/>
      <FitLocations points={points}/>
      {points.map(i => <CircleMarker key={i.id} center={[i.gateway.latitude, i.gateway.longitude]} radius={10}
        pathOptions={{color: i.state === 'resolved' ? '#166534' : '#b91c1c', fillOpacity: 0.8}}>
        <Popup><b>#{i.id} {i.title}</b><p>{i.message}</p><p>{i.gateway.latitude.toFixed(6)}, {i.gateway.longitude.toFixed(6)}</p></Popup>
      </CircleMarker>)}
    </MapContainer>
    <ul aria-label="Incident coordinates">{points.map(i => <li key={i.id}>#{i.id}: {i.gateway.latitude.toFixed(6)}, {i.gateway.longitude.toFixed(6)}</li>)}</ul>
  </section>;
}
