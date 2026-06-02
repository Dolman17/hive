document.addEventListener('DOMContentLoaded', function () {
    var mapElement = document.getElementById('consultantDirectoryMap');
    var dataElement = document.getElementById('consultantDirectoryMapData');

    if (!mapElement || !dataElement || typeof L === 'undefined') {
        return;
    }

    var consultants = [];
    try {
        consultants = JSON.parse(dataElement.textContent || '[]');
    } catch (error) {
        consultants = [];
    }

    var knownLocations = {
        london: [51.5072, -0.1276],
        birmingham: [52.4862, -1.8904],
        manchester: [53.4808, -2.2426],
        leeds: [53.8008, -1.5491],
        liverpool: [53.4084, -2.9916],
        bristol: [51.4545, -2.5879],
        cardiff: [51.4816, -3.1791],
        newcastle: [54.9783, -1.6178],
        nottingham: [52.9548, -1.1581],
        leicester: [52.6369, -1.1398]
    };

    function resolveCoords(location) {
        var normalised = String(location || '').toLowerCase().trim();
        for (var key in knownLocations) {
            if (normalised.indexOf(key) !== -1) {
                return knownLocations[key];
            }
        }
        return [54.5, -2.5];
    }

    var map = L.map(mapElement, { scrollWheelZoom: false }).setView([54.5, -2.5], 6);

    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: 'OpenStreetMap'
    }).addTo(map);

    var bounds = [];

    consultants.forEach(function (consultant, index) {
        var coords = resolveCoords(consultant.location);
        var offset = (index % 5) * 0.015;
        var latLng = [coords[0] + offset, coords[1] + offset];
        bounds.push(latLng);

        var marker = L.circleMarker(latLng, {
            radius: 10,
            color: consultant.accent || '#D4A017',
            fillColor: consultant.primary || '#0D1B2A',
            fillOpacity: 0.95,
            weight: 3
        }).addTo(map);

        marker.bindPopup('<strong>' + consultant.name + '</strong><br>' + consultant.location);
    });

    if (bounds.length > 1) {
        map.fitBounds(bounds, { padding: [40, 40] });
    } else if (bounds.length === 1) {
        map.setView(bounds[0], 9);
    }

    setTimeout(function () { map.invalidateSize(); }, 150);
});
