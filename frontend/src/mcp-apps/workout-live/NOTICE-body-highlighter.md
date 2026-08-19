# Third-party attribution: body silhouette SVG paths

The front/back muscle silhouette path data inlined in `workout-live.html`'s
`#muscle-map` (every `<path>` inside a `.body-base` or `.muscle` group) is vendored
from [`react-native-body-highlighter`](https://github.com/HichamELBSI/react-native-body-highlighter)
by Hicham ELABBASSI (`assets/bodyFront.ts` / `assets/bodyBack.ts`), MIT licensed.
Only the raw SVG path strings were taken — no code from that project ships here.

Front and back share one `1448×1448` coordinate space by construction (each view is
a `724`-wide half), which is why both `<svg>` elements in `workout-live.html` use a
plain `viewBox` slice of that space with no transform.

## License

```
MIT License

Copyright (c) 2022 ELABBASSI Hicham

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

The muscle-group *data* driving which regions light up (free-exercise-db's
`primaryMuscles`/`secondaryMuscles`, vendored into `backend/app/data/exercise_muscles.json`)
is separate and Unlicensed (public domain) — see that migration's docstring
(`backend/alembic/versions/20260818_1740_exercise_muscle_taxonomy_vendor_free_.py`).
