# Conductor

ground traffic control system

random digital twin test environment:
- airport structure
    - gate spawn nodes
    - runway nodes
    - intersection nodes
    - hold short nodes
    - taxiways(with individual turns)
    - nodes connecting each
- departing planes
    - spawn in random spawn nodes
    - random destination runway
    - store position, velocity, heading
- arriving planes
    - randomly flash to indicate arrival of a plane on runway
    - plane spawns and decelerates, exiting runway at closest exit
    - 

how to translate actual airports into image?
- QGIS to turn airport GIS data into exact nodes and edges(GEOJSON)
- pyQT simulation interface
- import GeoJSON data into python to turn into node graph
- planes are directed to go to each node, but follow a polyline path to display visually

layer-by-layer
- layer 1: just image of airport
- layer 2(invisible): node graph
- layer 3: planes moving
- layer 4: plane data