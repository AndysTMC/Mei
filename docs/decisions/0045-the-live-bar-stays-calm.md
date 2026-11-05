# 0045. The Live bar stays one height and moves only with emphasis; Live shows no spinner

Status: accepted
Date: 2026-11-05
Deciders: owner
Supersedes: 0040 (in part: Speaking's taller bar; sound moving the dots from its first trace)
Superseded-by: —

## Context

Seen on a real session, the Live bar of decision 0040 was busier than meant. While Mei spoke, its dots stayed stretched into short bars most of the time. While listening, a room's hum kept them slightly tall, and the slow wave of thinking and pausing stretched them too. Speaking's taller bar made the drawing as tall as its tallest look, so in the other states the bar floated in empty space and the row around it looked misplaced. In Live, the loading spinner also showed above the bar, saying twice that Mei was working.

## Decision

- **One height for every state:** 22 px, the Live button's own. Speaking is still told apart by its fill, with its dots cut out.
- **A floor for each state's sound.** Below it, nothing moves: about a quarter of the scale while listening (a room's hum) and nearly half while speaking (Mei's steady voice). Above it, the dots answer to emphasis.
- **Less stretch:** 0.35 of the room while listening and 0.15 while speaking. Spread and brightness carry the rest.
- **The idle wave only brightens.** Thinking and pausing keep their dots round.
- **No spinner in Live,** in the small or the large popup: the bar is what says Mei is working.
- **The row and the bar share the popup's 10 px gutters.** The buttons sit 8 px apart, so the screen button, the Live button and the bar line up on both edges.

## Consequences

`tests/voiceBar.test.ts` adds that a hum and Mei's steady voice leave the dots round, that thinking's dots stay round, and that every state has the same height. The nested Shell run's screenshots show the speaking and listening bars aligned with the row above them.
