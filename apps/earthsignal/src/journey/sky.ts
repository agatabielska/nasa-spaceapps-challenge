// Where the About camera is looking (radians). The starfield shifts by it, so the whole sky sweeps past while the
// camera flies around the globe. Plain shared state: the About scene writes it every frame, the starfield reads it.
export const sky={lon:0,lat:0};
