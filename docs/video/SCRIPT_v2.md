# Common Ground — "The Jezero crew" (video v2)

Story of the intended use: a crew going to Mars uses Common Ground to find ground on Earth that behaves like their
landing site, trains there, and lands well. Animated scenes are drawn with code (no AI images); every screen of the
app is a real capture; every number comes from the facts ledger. A small "Dramatization" tag is on screen in the
story scenes. English on screen; optional voice-over (Windows TTS or Mario's voice).

## 30 s cut (submission)

| Time | Picture | On screen / voice-over |
|---|---|---|
| 0–4 s | Night launch pad. A crew of four in silhouette walks to the rocket; Mars rises behind it. | *Four astronauts will land at Jezero crater, Mars.* |
| 4–9 s | Mission room, drawn. On the big screen, the real app: Mars globe, Jezero chosen, the line to the small Earth, the 10 options. | *First question: where on Earth is the ground like Jezero?* · *Common Ground: Tagant, Mauritania.* |
| 9–14 s | Desert at dawn drawn from the real Tagant relief profile. A rover and the crew train; a dust trail. Inset: the levelled comparison, Mars ochre over Earth sage. | *Same steepness: 6.8° on Mars, 6.6° on Earth. They practise landing and driving there.* |
| 14–17 s | Two quick cards slide in. | *What Earth cannot teach: gravity 3.73 m/s², pressure 636 Pa. Those they train in simulators.* |
| 17–21 s | Cruise: the ship crosses black space, Mars grows to fill the frame. | *Months later…* |
| 21–26 s | Descent over the real Jezero relief (NASA CTX), coral zones = steeper than the 15° limit; the lander steers to the green ring. | *The ground below looks like the ground they trained on.* |
| 26–30 s | Touchdown, dust settles, the rover rolls out; then end card. | *Mission success.* · **Common Ground — rehearse Mars and the Moon on Earth.** · Data: NASA · Team marsvia |

## 60 s cut (YouTube), adds after 17 s

| Time | Picture | On screen / voice-over |
|---|---|---|
| +6 s | The Mars globe with the coral points; the counter 95.4% / 4.6%. | *Earth can rehearse 95.4% of measured Mars. For the other 4.6%, robots go first.* |
| +8 s | "How it's built": the engine chain diagram (docs/how_it_works.svg) drawn step by step. | *NASA elevation models → the same three measures on both worlds → exact search over 2,730 Earth places → a facts ledger behind every number.* |
| +6 s | The Moon: south pole, Artemis III regions; the permanent-base layer (light, permanent shadow, Earth in view). | *The same for a permanent Moon base. Its low polar Sun is the part Earth cannot rehearse.* |
| +5 s | Validation card, honest. | *We report our tests as they came out.* (External validation result, once available.) |

## Production notes

- Base: the HyperFrames project in `video/` (index.html, assets). New drawn assets: crew silhouettes, rocket, mission room,
  desert from the Tagant profile (`video/make_assets.py` extends to a side profile from `height.bin`), ship in cruise.
- Real captures: app screens at 1920×1080 (re-take after the step-1 screen change).
- Numbers to check before render: 6.8° / 6.6° (Jezero vs Tagant, card), 3.73 m/s² and 636 Pa (bodies.json),
  95.4% / 4.6% (facts.json), 2,730 (facts.json), 15° (missions.json).
- Honesty: "Mission success" is the story; on screen the tag says "Dramatization of the intended use". We never say
  the tool predicts mission success (the site states it is not a success probability).
