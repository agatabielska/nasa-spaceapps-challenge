# Landing page: research, imagery and scientific wording

> **Note (15 November 2026).** The landing page was redesigned as a scroll-driven journey built on our own case studies (see README, “Landing and explorer”). Of the assets below only `earth-blue-marble.jpg` is still used; the Limpopo comparison and the spacecraft illustration were removed from `public/media/`. The research notes are kept for reference.

Verified against official NASA, NASA/JPL and ISRO sources on 14 November 2026. This document records the editorial decisions behind the EarthSignal landing page. It is not a description of an implemented SAR processing pipeline.

## Assets included in the project

All paths below are relative to `public/media/`. Images are served locally; visiting the page does not require fetching them from NASA. Original source pages remain linked in the interface for attribution and further reading.

| Local asset | Source and credit | Derivation and role |
| --- | --- | --- |
| `earth-blue-marble.jpg` | [NASA Earth Observatory — Blue Marble Next Generation, Base Map](https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/base-map/) | July 2004 global optical composite, resized from 5400 × 2700 to 2048 × 1024. Texture for the illustrative globe; not a NISAR image or live Earth observation. |
| `nisar-spacecraft.jpg` | [NASA — Artist’s Rendering of NISAR](https://science.nasa.gov/image-detail/amf-04a1b902-fbd2-4dec-9802-bb15e9631d82/), NASA/JPL-Caltech | JPEG web copy of the annotated PNG, reduced from 3550 × 1996 to 1500 × 843. Introduces the instruments and NASA–ISRO collaboration. An artist’s concept, not an in-orbit photograph. |
| `limpopo-before.jpg` | [NASA SVS 5661 — NISAR Reveals Major Flooding in Mozambique](https://svs.gsfc.nasa.gov/5661/), visualization by Zoey N. Armstrong; science advisors Alexandra Christensen and Bruce Chapman, NASA/JPL-Caltech | JPEG web copy of `Pre_OverviewComposite.png`; 1920 × 1080 retained. Observation from 5 January 2026. |
| `limpopo-during.jpg` | Same NASA SVS source and credits | JPEG web copy of `Post_OverviewComposite.png`; 1920 × 1080 retained. Observation from 17 January 2026, **during flooding**. |
| `limpopo-legend.png` | Same NASA SVS source | Original `Colorbar_simpletext.png`, 1500 × 1500, retained as the reference legend. |

Direct original downloads:

- [Blue Marble July 2004](https://assets.science.nasa.gov/content/dam/science/esd/eo/images/bmng/bmng-base/july/world.200407.3x5400x2700.jpg)
- [Annotated NISAR concept](https://assets.science.nasa.gov/dynamicimage/assets/science/missions/nisar/nisar-jpl/images/NISAR_Beauty_02-annotated.png)
- [Mozambique: before](https://svs.gsfc.nasa.gov/vis/a000000/a005600/a005661/Pre_OverviewComposite.png)
- [Mozambique: during flooding](https://svs.gsfc.nasa.gov/vis/a000000/a005600/a005661/Post_OverviewComposite.png)
- [Mozambique: color legend](https://svs.gsfc.nasa.gov/vis/a000000/a005600/a005661/Colorbar_simpletext.png)

The web copies reduce delivery size. They preserve the source imagery rather than inventing observations; lossy JPEG copies are presentation assets, not inputs for quantitative analysis. The globe’s lighting and Orbit’s decorative path are interface illustrations, not physical mission simulations.

## How to describe the comparison

The two Mozambique frames use matching geography and NASA’s consistent color scaling, so they support a before/during slider. The later date must not be described as the recovery after floodwaters receded. This is a NASA-prepared GCOV visualization, not a change layer calculated by EarthSignal.

NASA assigns HH to red, HV to green and their ratio to blue. In this particular visualization, dark blue indicates open water, green includes vegetation volume scattering, and magenta can suggest flooded forest. These colors are interpretive clues, not a universal SAR classification or validated damage map. Changing water appearance alone does not establish affected population, crop loss or flood volume. [Source and complete credits](https://svs.gsfc.nasa.gov/5661/).

The separate Sentinel-2 image already present in the workspace is from 29 January and has a different frame. It was not selected for the pixel-aligned slider. Images from the IIRS Jhilmil article are useful further reading but have a smaller presentation size and require a separate reuse-rights check before inclusion.

## Supported mission claims

| Suitable copy | Scope and source |
| --- | --- |
| “Radar observes the surface at night and through cloud cover.” | Radar supplies its own signal. Compare this advantage with optical imaging without claiming universal superiority. [NASA — Get to Know SAR](https://science.nasa.gov/mission/nisar/get-to-know-sar/) |
| “Two radar wavelengths provide different perspectives on land, vegetation and ice.” | L-band is about 24 cm and S-band 9.4 cm. L-band acquisition is global; S-band targets India and selected sites. Do not imply two-band coverage of every location. [NASA — Mission Overview](https://science.nasa.gov/mission/nisar/mission-overview/) |
| “A 12-day repeat orbit supports systematic comparisons.” | Exact-repeat cadence is distinct from continuous monitoring. Ascending and descending observations have different viewing geometries; do not automatically treat them as an interferometric pair. [NASA — Mission Overview](https://science.nasa.gov/mission/nisar/mission-overview/) |
| “SweepSAR combines a wide imaging swath — around 240 km — with fine spatial detail.” | The electronically steered receiving beam follows returning echoes across the reflector/feed. NASA describes a swath greater than 240 km and identifies scan-on-receive as the innovation enabling this combination. [NASA — About the Satellite](https://science.nasa.gov/mission/nisar/about-the-satellite/) |
| “Repeated observations help scientists study surface motion, ice and ecosystems.” | Centimeter-scale displacement measurement concerns interferometric processing under suitable conditions, not centimeter-sized image pixels. SAR image resolution is mode-dependent, approximately 3–10 m in NASA’s overview. [JPL — Science](https://www.jpl.nasa.gov/press-kits/nisar/mission-overview/science/), [NASA — Mission Overview](https://science.nasa.gov/mission/nisar/mission-overview/) |

### SweepSAR verification

NASA’s [detailed SweepSAR explanation](https://nisar.jpl.nasa.gov/mission/get-to-know-sar/sweepsar/) describes transmitting across the full ground swath and receiving independently with elements of the phased-array feed. It specifies a 242 km illuminated swath and explains how electronic receive scanning combines wide coverage with fine resolution. “Around 240 km” is appropriate concise landing-page wording; it avoids implying every processing mode or product has identical dimensions.

The [ISRO S-band data release of 24 July 2026](https://www.isro.gov.in/NISARS_Band_SAR_Data_Products_Release.html) independently describes the 12 m reflector, SweepSAR and the approximately 240 km wide-swath/high-resolution combination. The physical antenna does not need to spin for the electronic receive scan.

## Further material worth adding

1. **[NASA SVS 5615 — NISAR satellite orbit](https://svs.gsfc.nasa.gov/5615/).** Best supporting visual for explaining the radar’s ground swath. Credit: NASA Scientific Visualization Studio / Kel Elkins. A [1920 × 1080 still, about 224 KB](https://svs.gsfc.nasa.gov/vis/a000000/a005600/a005615/nisar_orbit.02415_preview.jpg) can communicate the idea without autoplay video. The page also offers a 1080p animation of about 15.7 MB; load it only after a play action if added. Treat it as a mission visualization, not live tracking. The landing footer already links to the source.

2. **[NASA SVS 31360 — NISAR First Light Imagery](https://svs.gsfc.nasa.gov/31360/).** Forest River, North Dakota, and Mount Desert Island, Maine, provide an additional ecosystem and land-cover story alongside the flood example. The page offers 1080p videos of roughly 8.7 MB and 6.1 MB. Attribute NASA/JPL-Caltech mission imagery and preserve the source’s full credits, including NASA SVS technical support by Nathan Marder. These are initial observations from August 2025, not before/after disaster assessments. Avoid applying the Mozambique color legend to them without checking their own descriptions.

3. **[NASA — Get to Know SAR](https://science.nasa.gov/mission/nisar/get-to-know-sar/).** Suitable source for a short original diagram showing pulse, surface interaction, returning echo and repeated observation. The scientific mechanism should remain separate from Orbit’s language-model workflow.

4. **[JPL — NISAR science and applications](https://www.jpl.nasa.gov/press-kits/nisar/mission-overview/science/).** Supports examples involving wetlands, forests, ice, land deformation and natural hazards. Use short contextual cards and links rather than promising those analyses are available in the current app.

## Product wording boundary

EarthSignal currently offers an event catalog, map exploration, source references and local conversational navigation with Orbit. The landing page may explain the project’s intended analysis journey, but computed NISAR change layers and measured impacts remain future work. Documented study candidates and fictional demo scenarios must retain their separate labels.

NASA and ISRO are the mission partners and source providers. EarthSignal is an independent Space Apps team project; it must not imply official endorsement or that Orbit is part of the satellite mission.
