# Design system

Tokens live in `frontend/app/globals.css`. The base background is `#050c14`; raised background `#07121c`; panel `#091621`; borders `#142737` and `#213a4d`; text `#f0f5fa`; muted text `#8ea0b4`; positive/accent `#2dd4a0`; blue `#2f8de4`; cyan `#32c8dc`; amber `#e8b84d`; negative `#ff4d67`.

The spacing scale is 4/8/12/16/20/24 px, radii are 6/9/12 px, and panels use a restrained 12×32 px black shadow. Desktop uses a 202 px rail and 58 px header. At 1050 px the rail contracts; below 760 px navigation becomes horizontal, content becomes one column and long controls/tables scroll or collapse.

State semantics are consistent: green means verified positive/safe state, red means negative/error, amber means partial/stale/caution, blue means selected/informational, and neutral means unresolved. Scores are never coloured or labelled as probabilities. Focus rings use the accent token; reduced-motion disables transitions.
