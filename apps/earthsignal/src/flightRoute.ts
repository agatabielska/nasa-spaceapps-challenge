// Where along the flood trace each frame of the flight recording is (0 = trace origin, 1 = Syabrubesi), from the
// capture of data/event_visualisation/Nepal/map3d.html. This recording places its 132 frames evenly by distance.
export const flightDistance=Array.from({length:132},(_,i)=>i/131);
