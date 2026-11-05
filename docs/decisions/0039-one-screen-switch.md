# 0039. One switch decides whether Mei looks at the screen without asking

Status: accepted
Date: 2026-11-05
Deciders: owner
Supersedes: 0029 (in part: Live looks without asking), 0035 (in part: "Hey Mei" looks without asking)
Superseded-by: —

## Context

Decision 0029 let Mei look at the screen without asking when the request came from Live, and decision 0035 did the same for "Hey Mei". In chat it asked unless a setting ("Look at the screen without asking") was on. The owner asked for a screen button beside Live (on 2026-10-25), and on 2026-11-05 asked that nothing be special about how a request came: Mei looks unasked only while that switch is on.

## Decision

- **One switch:** `computer.see_without_asking`. On, Mei looks at the screen without asking. Off, it asks every time, whether the request was typed, said in Live, or started with "Hey Mei".
- **A screen button beside Live** (`video-display-symbolic`) flips the switch. It is filled in while on, and shown once Mei may use the computer. The row in Settings is the same switch, so the two always agree.

## Consequences

- With the switch off, a spoken "What's on my screen?" shows an approval card, answered on screen. Mei says the OK is on screen: a voice may approve only local changes that can be undone (§11.6), and showing the screen to a model is not one. Grants ("this task", "always") work as before.
- The switch is global, not per chat: turning it on lasts until it is turned off.
