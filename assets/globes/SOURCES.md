# Globe textures: sources, credits and licences

All three files are equirectangular JPEGs, 2048 x 1024 pixels, RGB, north up, longitude 0 at the centre of the image.
They were made on 2026-11-14 from the sources below by `rasterio` (area-average resampling), quality 88.

| File | Size (bytes) | Body | Source page (URL read) | Source file used | Credit line | Licence / terms |
|---|---|---|---|---|---|---|
| `moon.jpg` | 453,084 | Moon | https://svs.gsfc.nasa.gov/4720 (NASA SVS, "CGI Moon Kit") | `https://svs.gsfc.nasa.gov/vis/a000000/a004700/a004720/lroc_color_2k.jpg` (LROC colour map, 2048 x 1024, used unchanged) | NASA Scientific Visualization Studio, CGI Moon Kit (LROC colour map). Full credits page on the SVS site was not read. | NASA media usage guidelines (https://www.nasa.gov/nasa-brand-center/images-and-media/, read 2026-11-14): NASA should be acknowledged as the source; NASA insignia and logotype are not public domain. Not formally public domain. |
| `earth.jpg` | 276,487 | Earth | https://commons.wikimedia.org/wiki/File:Blue_Marble_2002.png (Wikimedia Commons; the NASA Visible Earth image) | 4096 x 2048 thumbnail returned by the Commons API (`iiurlwidth=4096`), actual file 3840 x 1920, downscaled to 2048 x 1024 | "Blue Marble" image, NASA Visible Earth: "Blue Marble: Land Surface, Shallow Water, and Shaded Topography" (https://visibleearth.nasa.gov/images/57752/blue-marble-land-surface-shallow-water-and-shaded-topography); NASA Goddard Space Flight Center; image by Reto Stöckli, enhancements by Robert Simmon (Commons 'Artist' field). | Public domain (Commons licence field, read 2026-11-14; 'Credit' field names NASA Visible Earth). |
| `mars.jpg` | 527,185 | Mars | https://commons.wikimedia.org/wiki/File:Mars_Viking_MDIM21_ClrMosaic_1km.jpg (Wikimedia Commons copy of the USGS product; underlying USGS record https://astrogeology.usgs.gov/search/details/Mars/Viking/MDIM21/Mars_Viking_MDIM21_ClrMosaic_global_232m/cub, named in the Commons 'Credit' field) | 21339 x 10670 JPEG (36.7 MB), downscaled to 2048 x 1024 | NASA / Jet Propulsion Laboratory / USGS (Commons 'Artist' field): Viking MDIM 2.1 colour global mosaic | Public domain (Commons licence field 'pd', read 2026-11-14). The USGS copyright page (https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits) states USGS-produced data are in the U.S. Public Domain. |

Notes

- The Earth texture is the 2002 Blue Marble composite named in the Commons file (not a current composite).
- `earth.jpg` was first made from a NASA GEBCO elevation map (greyscale, checked: no colour) and rejected. Only the final file is kept.
- The Mars source is 1 km per pixel, resampled to 2048 x 1024 (about 10 km per pixel at the equator).
- Each texture is <= 5 MB (largest 527 KB).
