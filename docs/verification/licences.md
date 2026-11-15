# Licence verification: open items from REPO_CHECKLIST must-fix 4-5

Checked 2026-11-15 by reading the provider pages (WebFetch). WebFetch returns text summarised by a small model, so
each quote below is the sentence as returned; the page itself should be re-read before the repository is published.

## 1. NASADEM HGT v001 (must-fix 5)

Status: **resolved by the producer's own statement.** Mario's sign-off is still required (checklist must-fix 5: "Mario
confirms the answer and it is recorded").
- Verified in browser 2026-11-15: "This dataset is openly shared, without restriction, in accordance with the EOSDIS Data Use and Citation Guidance." (screenshot: docs/verification/licences/nasadem.png)

- URL: https://www.earthdata.nasa.gov/data/catalog/lpcloud-nasadem-hgt-001 (NASA Earthdata catalog record, LP DAAC)
  - Quote: "This dataset is openly shared, without restriction, in accordance with the EOSDIS Data Use and Citation Guidance."
  - Producer: LP DAAC archives and distributes; NASA JPL is credited as author.
- URL: https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance (EOSDIS Data Use and Citation Guidance)
  - Quote: "While there are no restrictions on the use of these data, data users are very strongly urged to cite the data used in their work products."
  - Quote: "Non-NASA data available through the ESDIS project is subject to the license arrangements of the sponsoring organization."
    NASADEM is a NASA JPL / USGS product distributed by LP DAAC, so the first quote applies, not the second.
  - Verified in browser 2026-11-15: "While there are no restrictions on the use of these data, data users are very strongly urged to cite the data used in their work products." (screenshot: docs/verification/licences/earthdata_guidance.png)
- Conflicting label: Planetary Computer STAC metadata says "proprietary". This is a STAC catalogue label and is not a
  licence text. It is superseded by the Earthdata record above. Keep the note in the references so the conflict is visible.
- Required in use: citation of the dataset (DOI 10.5067/MEASURES/NASADEM/NASADEM_HGT.001) and NASA as source. No
  endorsement implied.

## 2. LROC NAC DTM Apollo 17, 5 m (must-fix 4)

Status: **resolved.** Public domain for products on the LROC Data Node of the PDS.

- Verified in browser 2026-11-15: "Data products available through the LROC Data Node of the PDS or through NASA PDS interfaces are in the public domain (see list of URLs below)." and "For news media or educational purposes, credit LROC images with the text tag NASA/GSFC/Arizona State University." (screenshot: docs/verification/licences/lroc.png)

- URL: https://lroc.im-ldi.com/about/terms (LROC Terms of Use)
  - Quote: "Data products available through the LROC Data Node of the PDS or through NASA PDS interfaces are in the public domain"
  - Credit (media and educational use): "credit LROC images with the text tag NASA/GSFC/Arizona State University." Shorter form also accepted: "NASA/GSFC/ASU".
- Product path: https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/DATA/SDP/NAC_DTM/APOLLO17/
  This URL returns a 302 redirect to the NASA PDS data store (https://pds.mcp.nasa.gov/data/index.html#/...). The redirected
  page is a client-side app and was not readable, so the product-level licence page was not read. The terms above cover
  the PDS node products, which is the basis for the resolution.

## Other rows touched in this pass

- USGS CTX DTMs (InSight, Spirit, Zhurong, Oxia): USGS public domain policy (https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits); STAC collection record states CC0-1.0 (https://stac.astrogeology.usgs.gov/api/collections/mro_ctx_controlled_usgs_dtms). Already in `site/REFERENCES.md` and `site/references.html`.
- Natural Earth (public domain, no attribution required) and Köppen-Geiger Beck et al. 2018 (CC BY 4.0): already recorded in both references files. Not re-read in this pass.
- ESA WorldCover (CC BY 4.0), Gale figshare tile (CC BY 4.0), NASA SVS CGI Moon Kit texture (NASA media guidelines): already recorded. Not re-read in this pass.

## Open after this pass

- Mario sign-off on NASADEM (checklist must-fix 5).
- Copernicus DEM GLO-30 notice (COP-DEM licence Art. 6(a) and 6(c)): recorded in the references files only. Not in the site footer line. Decide whether the on-page credit needs it.
- LOLA / PGDA product 78 and 90: no licence text on the product page (cite-as-requested). Unchanged.
