# Verificacion independiente: lugar y pais de los gemelos (muestra)

Lector propio de shapefile (Python puro, struct). Admin-1 Natural Earth 5.1.1 y populated places Natural Earth 5.1.2. Semilla 20261114.

## Diseno de muestra

- Estrato: pais del gemelo. 34 paises en las 160 fichas; n=30 no alcanza para cubrir todos, se cubren 30 con 1 ficha cada uno (max 3 por pais no obliga). No cubiertos (sorteo): India, Niger, Pakistan, United States of America.
- Fichas con match distinto de 'inside': 0 de 160 (estrato vacio, 0 de 10 posibles).
- n total = 30.

## Tasas (Wilson 95%)

| Campo | k/n | p | Wilson 95% |
|---|---|---|---|
| admin1 | 30/30 | 1.000 | [0.886, 1.000] |
| country | 30/30 | 1.000 | [0.886, 1.000] |
| match | 30/30 | 1.000 | [0.886, 1.000] |
| nearest_town_name | 30/30 | 1.000 | [0.886, 1.000] |
| nearest_town_country | 30/30 | 1.000 | [0.886, 1.000] |
| nearest_town_distance | 30/30 | 1.000 | [0.886, 1.000] |

## Discrepancias

Ninguna.

## Detalle

| estrato | ficha | admin1 | country | match | pueblo ficha | pueblo recomp | km ficha | km recomp |
|---|---|---|---|---|---|---|---|---|
| Afghanistan | haworth__haworth__pool__pool_01467.json | Hilmand / Hilmand | Afghanistan / Afghanistan | inside / inside | Tarin Kowt (Afghanistan) | Tarin Kowt (Afghanistan) | 94.49 | 94.491 |
| Algeria | jezero__jezero__pool__pool_01394.json | Ouargla / Ouargla | Algeria / Algeria | inside / inside | Dehibat (Tunisia) | Dehibat (Tunisia) | 184.83 | 184.83 |
| Angola | gale__gale__pool__pool_00103.json | Benguela / Benguela | Angola / Angola | inside / inside | Benguela (Angola) | Benguela (Angola) | 77.53 | 77.528 |
| Argentina | gale__gale__pool__pool_00001.json | Santa Cruz / Santa Cruz | Argentina / Argentina | inside / inside | Comondante Luis Piedrabuena (Argentina) | Comondante Luis Piedrabuena (Argentina) | 24.14 | 24.138 |
| Bolivia | im2_athena__im2_athena__pool__pool_00084.json | Potosí / Potosí | Bolivia / Bolivia | inside / inside | Villa Martin (Bolivia) | Villa Martin (Bolivia) | 53.07 | 53.072 |
| Chad | oxia_planum__oxia_planum__pool__pool_00162.json | Kanem / Kanem | Chad / Chad | inside / inside | Mao (Chad) | Mao (Chad) | 213.88 | 213.884 |
| Chile | cabeus_b_peak__cabeus_b_peak__pool__pool_00091.json | Tarapacá / Tarapacá | Chile / Chile | inside / inside | Pozo Almonte (Chile) | Pozo Almonte (Chile) | 68.86 | 68.864 |
| China | nobile_rim_2__nobile_rim_2__pool__pool_01549.json | Xizang / Xizang | China / China | inside / inside | Quiemo (China) | Quiemo (China) | 462.11 | 462.112 |
| Egypt | spirit_columbia__spirit_columbia__pool__pool_00961.json | Al Bahr al Ahmar / Al Bahr al Ahmar | Egypt / Egypt | inside / inside | Qena (Egypt) | Qena (Egypt) | 70.95 | 70.952 |
| Eritrea | apollo17_taurus_littrow__apollo17_taurus_littrow__pool__pool_00151.json | Debub / Debub | Eritrea / Eritrea | inside / inside | Massawa (Eritrea) | Massawa (Eritrea) | 84.78 | 84.777 |
| Ethiopia | mons_mouton_plateau__mons_mouton_plateau__pool__pool_00117.json | Afar / Afar | Ethiopia / Ethiopia | inside / inside | Dikhil (Djibouti) | Dikhil (Djibouti) | 125.85 | 125.848 |
| Iran | de_gerlache_rim_2__de_gerlache_rim_2__pool__pool_00975.json | Sistan and Baluchestan / Sistan and Baluchestan | Iran / Iran | inside / inside | Turbat (Pakistan) | Turbat (Pakistan) | 93.0 | 93.002 |
| Israel | gale__gale__pool__pool_01287.json | HaDarom / HaDarom | Israel / Israel | inside / inside | Al Aqabah (Jordan) | Al Aqabah (Jordan) | 63.62 | 63.619 |
| Jordan | gale__gale__pool__pool_01344.json | Ma`an / Ma`an | Jordan / Jordan | inside / inside | An Nabk (Saudi Arabia) | An Nabk (Saudi Arabia) | 54.49 | 54.49 |
| Libya | jezero__jezero__pool__pool_01135.json | Ash Shati' / Ash Shati' | Libya / Libya | inside / inside | Birak (Libya) | Birak (Libya) | 154.05 | 154.053 |
| Mali | gale__gale__pool__pool_00700.json | Timbuktu / Timbuktu | Mali / Mali | inside / inside | Chegga (Mauritania) | Chegga (Mauritania) | 179.71 | 179.71 |
| Mauritania | spirit_columbia__spirit_columbia__pool__pool_00336.json | Tagant / Tagant | Mauritania / Mauritania | inside / inside | Tidjikdja (Mauritania) | Tidjikdja (Mauritania) | 72.08 | 72.076 |
| Mongolia | mons_mouton_plateau__mons_mouton_plateau__pool__pool_01945.json | Hovd / Hovd | Mongolia / Mongolia | inside / inside | Hami (China) | Hami (China) | 253.92 | 253.922 |
| Morocco | de_gerlache_rim_2__de_gerlache_rim_2__pool__pool_01247.json | Souss - Massa - Draâ / Souss - Massa - Draâ | Morocco / Morocco | inside / inside | Agadir (Morocco) | Agadir (Morocco) | 158.17 | 158.165 |
| Namibia | insight_elysium__insight_elysium__pool__pool_00086.json | Erongo / Erongo | Namibia / Namibia | inside / inside | Omaruru (Namibia) | Omaruru (Namibia) | 98.46 | 98.456 |
| Peru | de_gerlache_rim_2__de_gerlache_rim_2__pool__pool_00097.json | Tacna / Tacna | Peru / Peru | inside / inside | Tacna (Peru) | Tacna (Peru) | 26.1 | 26.099 |
| Russia | im1_odysseus__im1_odysseus__pool__pool_01993.json | Kamchatka / Kamchatka | Russia / Russia | inside / inside | Klyuchi (Russia) | Klyuchi (Russia) | 105.54 | 105.541 |
| Saudi Arabia | im2_athena__im2_athena__pool__pool_00737.json | Al Madinah / Al Madinah | Saudi Arabia / Saudi Arabia | inside / inside | Medina (Saudi Arabia) | Medina (Saudi Arabia) | 90.59 | 90.585 |
| Somalia | nobile_rim_1__nobile_rim_1__pool__pool_00112.json | Bari / Bari | Somalia / Somalia | inside / inside | Boosaaso (Somalia) | Boosaaso (Somalia) | 51.03 | 51.027 |
| Sudan | spirit_columbia__spirit_columbia__pool__pool_00616.json | Northern / Northern | Sudan / Sudan | inside / inside | Al Jawf (Libya) | Al Jawf (Libya) | 362.05 | 362.052 |
| Tunisia | gale__gale__pool__pool_01488.json | Tataouine / Tataouine | Tunisia / Tunisia | inside / inside | Tataouine (Tunisia) | Tataouine (Tunisia) | 46.95 | 46.952 |
| Turkmenistan | jezero__jezero__pool__pool_01824.json | Tashauz / Tashauz | Turkmenistan / Turkmenistan | inside / inside | Koneurgench (Turkmenistan) | Koneurgench (Turkmenistan) | 102.33 | 102.327 |
| United Arab Emirates | zhurong__zhurong__pool__pool_00748.json | Abu Dhabi / Abu Dhabi | United Arab Emirates / United Arab Emirates | inside / inside | Al Ayn (United Arab Emirates) | Al Ayn (United Arab Emirates) | 93.49 | 93.486 |
| Uzbekistan | insight_elysium__insight_elysium__pool__pool_01862.json | Karakalpakstan / Karakalpakstan | Uzbekistan / Uzbekistan | inside / inside | Qunghirot (Uzbekistan) | Qunghirot (Uzbekistan) | 169.53 | 169.529 |
| Yemen | cabeus_b_peak__cabeus_b_peak__pool__pool_00138.json | Hadramawt / Hadramawt | Yemen / Yemen | inside / inside | Al Mukalla (Yemen) | Al Mukalla (Yemen) | 116.41 | 116.409 |
