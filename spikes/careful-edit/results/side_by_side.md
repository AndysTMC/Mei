# Every output, case by case

### f01 (fillers)

| option | output | flag |
|---|---|---|
| ref | Can you open the downloads folder? |  |
| (raw words, untouched) | um can you uh open the the downloads folder |  |
| asr-kroko | Um, can you open the downloads folder? |  |
| asr-moonshine-base | Um, can you open the downloads folder? |  |
| asr-moonshine-tiny | Um, can you uh, open the downloads folder? |  |
| lfm2.5-1.2b | Can you open the downloads folder? |  |
| lfm2.5-1.2b+guard | Can you open the downloads folder? |  |
| lfm2.5-1.2b@rules | Can you open the downloads folder? |  |
| lfm2.5-1.2b+guard@rules | Can you open the downloads folder? |  |
| punct-ct+guard@rules | Can you open the downloads folder? |  |
| punct-ct | um can you uh open the the downloads folder？ |  |
| punct-en+guard>t5-small-gec+guard@rules | Can you open the downloads folder? |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Can you open the downloads, folder? |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | Can you open the downloads folder? |  |
| punct-en+guard>t5-tiny+guard@rules | Can you open the downloads folder? |  |
| punct-en+guard@kroko+rules | Can you open the downloads, folder? |  |
| punct-en+guard@rules#t2 | Can you open the downloads folder? |  |
| punct-en+guard@rules | Can you open the downloads folder? |  |
| punct-en | UM, can you uh open the the downloads? Folder |  |
| qwen2.5-0.5b | Could you open the downloads folder? | reworded +could, -can |
| qwen2.5-0.5b+guard | Um can you open the downloads folder? |  |
| qwen2.5-0.5b@kroko+rules | Can you open the downloads folder? |  |
| qwen2.5-0.5b+guard@kroko+rules | Can you open the downloads folder? |  |
| qwen2.5-0.5b@rules#t2 | Can you open the downloads folder? |  |
| qwen2.5-0.5b+guard@rules#t2 | Can you open the downloads folder? |  |
| qwen2.5-0.5b@rules | Can you open the downloads folder? |  |
| qwen2.5-0.5b+guard@rules | Can you open the downloads folder? |  |
| qwen3-0.6b | Um can you open the downloads folder? |  |
| qwen3-0.6b+guard | Um can you open the downloads folder? |  |
| qwen3-0.6b@rules | Can you open the downloads folder? |  |
| qwen3-0.6b+guard@rules | Can you open the downloads folder? |  |
| rules+ | Can you open the downloads folder? |  |
| rules+@kroko+rules | Can you open the downloads folder? |  |
| rules+@kroko | Can you open the downloads folder? |  |
| rules-seam | Can you open the downloads folder |  |
| rules-seam@kroko | Can you open the downloads folder? |  |
| t5-base | Um, can you uh open the downloads folder? |  |
| t5-base+guard | Um, can you uh open the downloads folder? |  |
| t5-base@kroko+rules | Can you open the downloads folder? |  |
| t5-base+guard@kroko+rules | Can you open the downloads folder? |  |
| t5-base@rules | Can you open the downloads folder? |  |
| t5-base+guard@rules | Can you open the downloads folder? |  |
| t5-mini | and can you just open the downloads folder? | reworded +and, +just |
| t5-mini+guard | Um can you uh open the downloads folder? |  |
| t5-mini@rules#t2 | Can you open the downloads folder? |  |
| t5-mini+guard@rules#t2 | Can you open the downloads folder? |  |
| t5-mini@rules | Can you open the downloads folder? |  |
| t5-mini+guard@rules | Can you open the downloads folder? |  |
| t5-small-gec | um can you uh open the downloads folder |  |
| t5-small-gec+guard | Um can you uh open the downloads folder. |  |
| t5-small-gec@kroko+rules | Can you open the downloads folder? |  |
| t5-small-gec+guard@kroko+rules | Can you open the downloads folder? |  |
| t5-small-gec@rules#t2 | Can you open the downloads folder? |  |
| t5-small-gec+guard@rules#t2 | Can you open the downloads folder? |  |
| t5-small-gec@rules | Can you open the downloads folder? |  |
| t5-small-gec+guard@rules | Can you open the downloads folder? |  |
| t5-small-synth | You can open the Windows Media folder and select the folder. | MEANING +media, +select, +windows, -downloads, lost 'downloads' |
| t5-small-synth+guard | Um can you uh open the the downloads folder. |  |
| t5-small-synth@rules | Can you open the slidesbook file? | MEANING +file, +slidesbook, -downloads, -folder, lost 'downloads' |
| t5-small-synth+guard@rules | Can you open the downloads folder? |  |
| t5-tiny+guard>punct-en+guard@rules | Can you open the downloads, folder? |  |
| t5-tiny | um can you just open the downloads folder? | reworded +just |
| t5-tiny+guard | Um can you uh open the downloads folder? |  |
| t5-tiny@kroko+rules | Can you open the downloads folder? |  |
| t5-tiny+guard@kroko+rules | Can you open the downloads folder? |  |
| t5-tiny@rules#t2 | Can you open the downloads folder? |  |
| t5-tiny+guard@rules#t2 | Can you open the downloads folder? |  |
| t5-tiny@rules | Can you open the downloads folder? |  |
| t5-tiny+guard@rules | Can you open the downloads folder? |  |

### f02 (fillers)

| option | output | flag |
|---|---|---|
| ref | So I was thinking we could move the meeting to Friday. |  |
| (raw words, untouched) | so um i was thinking we could like move the meeting to friday |  |
| asr-kroko | so Amai was thinking we could like move the meeting to Friday. | MEANING +amai |
| asr-moonshine-base | So, MI was thinking we could like move the meeting to Friday. | MEANING +mi |
| asr-moonshine-tiny | So, Am I was thinking we could like move the meeting to Friday? | reworded +am |
| lfm2.5-1.2b | Yeah, maybe we could shift the meeting to Friday. | MEANING +maybe, +shift, +yeah, -move, -thinking |
| lfm2.5-1.2b+guard | So um i was thinking we could like move the meeting to Friday. |  |
| lfm2.5-1.2b@rules | So I was thinking we could like move the meeting to friday |  |
| lfm2.5-1.2b+guard@rules | So I was thinking we could like move the meeting to friday. |  |
| punct-ct+guard@rules | So I was thinking we could like move the meeting to friday. |  |
| punct-ct | so um i was thinking we could like move the meeting to friday。 |  |
| punct-en+guard>t5-small-gec+guard@rules | So I was thinking we could like move the meeting to Friday. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | So Amai was thinking we could like move the meeting to Friday. | MEANING +amai |
| punct-en+guard>t5-tiny+guard@rules#t2 | So I was thinking we could like move the meeting to Friday. |  |
| punct-en+guard>t5-tiny+guard@rules | So I was thinking we could like move the meeting to Friday. |  |
| punct-en+guard@kroko+rules | So Amai was thinking we could like move the meeting to Friday. | MEANING +amai |
| punct-en+guard@rules#t2 | So I was thinking we could like move the meeting to Friday. |  |
| punct-en+guard@rules | So I was thinking we could like move the meeting to Friday. |  |
| punct-en | So UM, I was thinking we could like move the meeting to Friday. |  |
| qwen2.5-0.5b | So, I was thinking we could move the meeting to Friday. |  |
| qwen2.5-0.5b+guard | So, I was thinking we could like move the meeting to Friday. |  |
| qwen2.5-0.5b@kroko+rules | So Amai was thinking we could move the meeting to Friday. | MEANING +amai |
| qwen2.5-0.5b+guard@kroko+rules | So Amai was thinking we could like move the meeting to Friday. | MEANING +amai |
| qwen2.5-0.5b@rules#t2 | So I was thinking we could move the meeting to Friday. |  |
| qwen2.5-0.5b+guard@rules#t2 | So I was thinking we could like move the meeting to Friday. |  |
| qwen2.5-0.5b@rules | So I was thinking we could move the meeting to Friday. |  |
| qwen2.5-0.5b+guard@rules | So I was thinking we could like move the meeting to Friday. |  |
| qwen3-0.6b | So, um I was thinking we could move the meeting to Friday. |  |
| qwen3-0.6b+guard | So, um I was thinking we could like move the meeting to Friday. |  |
| qwen3-0.6b@rules | So I was thinking we could move the meeting to Friday. |  |
| qwen3-0.6b+guard@rules | So I was thinking we could like move the meeting to Friday. |  |
| rules+ | So I was thinking we could move the meeting to Friday. |  |
| rules+@kroko+rules | So Amai was thinking we could move the meeting to Friday. | MEANING +amai |
| rules+@kroko | So Amai was thinking we could move the meeting to Friday. | MEANING +amai |
| rules-seam | So I was thinking we could like move the meeting to friday |  |
| rules-seam@kroko | So Amai was thinking we could like move the meeting to Friday. | MEANING +amai |
| t5-base | So, um, I was thinking we could like move the meeting to friday. |  |
| t5-base+guard | So, um, I was thinking we could like move the meeting to friday. |  |
| t5-base@kroko+rules | So Amai was thinking we could like move the meeting to Friday. | MEANING +amai |
| t5-base+guard@kroko+rules | So Amai was thinking we could like move the meeting to Friday. | MEANING +amai |
| t5-base@rules | So I was thinking we could like move the meeting to friday. |  |
| t5-base+guard@rules | So I was thinking we could like move the meeting to friday. |  |
| t5-mini | So I was thinking we could move the meeting to Friday. |  |
| t5-mini+guard | So I was thinking we could like move the meeting to Friday. |  |
| t5-mini@rules#t2 | So I was thinking we could move the meeting to Friday. |  |
| t5-mini+guard@rules#t2 | So I was thinking we could like move the meeting to Friday. |  |
| t5-mini@rules | So I was thinking we could move the meeting to Friday. |  |
| t5-mini+guard@rules | So I was thinking we could like move the meeting to Friday. |  |
| t5-small-gec | So I was thinking we could move the meeting to Friday. |  |
| t5-small-gec+guard | So I was thinking we could like move the meeting to Friday. |  |
| t5-small-gec@kroko+rules | So Amai was thinking we could move the meeting to Friday. | MEANING +amai |
| t5-small-gec+guard@kroko+rules | So Amai was thinking we could like move the meeting to Friday. | MEANING +amai |
| t5-small-gec@rules#t2 | So I was thinking we could move the meeting to Friday. |  |
| t5-small-gec+guard@rules#t2 | So I was thinking we could like move the meeting to Friday. |  |
| t5-small-gec@rules | So I was thinking we could move the meeting to Friday. |  |
| t5-small-gec+guard@rules | So I was thinking we could like move the meeting to Friday. |  |
| t5-small-synth | so I was thinking we could move the meeting to friday. |  |
| t5-small-synth+guard | So I was thinking we could like move the meeting to friday. |  |
| t5-small-synth@rules | So I was thinking we could move the meeting to friday. |  |
| t5-small-synth+guard@rules | So I was thinking we could like move the meeting to friday. |  |
| t5-tiny+guard>punct-en+guard@rules | So I was thinking we could like move the meeting to Friday. |  |
| t5-tiny | So um I was thinking we could like to move to the meeting on Friday. | reworded +on, -to |
| t5-tiny+guard | So um I was thinking we could like move the meeting to Friday. |  |
| t5-tiny@kroko+rules | So I was thinking we could like to move to the meeting on Friday. | reworded +on, -to |
| t5-tiny+guard@kroko+rules | So Amai was thinking we could like move the meeting to Friday. | MEANING +amai |
| t5-tiny@rules#t2 | So I was thinking we could like to move to the meeting on Friday. | reworded +on, -to |
| t5-tiny+guard@rules#t2 | So I was thinking we could like move the meeting to Friday. |  |
| t5-tiny@rules | So I was thinking we could like to move to the meeting on Friday. | reworded +on, -to |
| t5-tiny+guard@rules | So I was thinking we could like move the meeting to Friday. |  |

### f03 (fillers)

| option | output | flag |
|---|---|---|
| ref | What's the weather tomorrow? |  |
| (raw words, untouched) | uh hmm what's the weather tomorrow |  |
| asr-kroko | Ah, him what's the weather tomorrow? | MEANING +ah |
| asr-moonshine-base | Uh-huh, what's the weather tomorrow? | MEANING +uh-huh |
| asr-moonshine-tiny | O, him, what's the weather to-morrow? | MEANING +o, +to-morrow, -tomorrow, lost 'tomorrow' |
| lfm2.5-1.2b | weather/whether | MEANING +weather/whether, -tomorrow, -weather, -what's, lost 'tomorrow' |
| lfm2.5-1.2b+guard | Uh hmm what's the weather tomorrow. |  |
| lfm2.5-1.2b@rules | What's the weather tomorrow? |  |
| lfm2.5-1.2b+guard@rules | What's the weather tomorrow? |  |
| punct-ct+guard@rules | What's the weather tomorrow? |  |
| punct-ct | uh，hmm，what's the weather tomorrow？ | MEANING +uh，hmm，what's, -what's |
| punct-en+guard>t5-small-gec+guard@rules | What's the weather tomorrow? |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Ah, him, what's the weather tomorrow? | MEANING +ah |
| punct-en+guard>t5-tiny+guard@rules#t2 | What's the weather tomorrow? |  |
| punct-en+guard>t5-tiny+guard@rules | What's the weather tomorrow? |  |
| punct-en+guard@kroko+rules | Ah, him, what's the weather tomorrow? | MEANING +ah |
| punct-en+guard@rules#t2 | What's the weather tomorrow? |  |
| punct-en+guard@rules | What's the weather tomorrow? |  |
| punct-en | UH, hmm, what's the weather tomorrow? |  |
| qwen2.5-0.5b | Uh, hmm, what's the weather tomorrow? |  |
| qwen2.5-0.5b+guard | Uh, hmm, what's the weather tomorrow? |  |
| qwen2.5-0.5b@kroko+rules | Ah, what's the weather tomorrow? | MEANING +ah |
| qwen2.5-0.5b+guard@kroko+rules | Ah, him what's the weather tomorrow? | MEANING +ah |
| qwen2.5-0.5b@rules#t2 | What's the weather tomorrow? |  |
| qwen2.5-0.5b+guard@rules#t2 | What's the weather tomorrow? |  |
| qwen2.5-0.5b@rules | What's the weather tomorrow? |  |
| qwen2.5-0.5b+guard@rules | What's the weather tomorrow? |  |
| qwen3-0.6b | Uh, what's the weather tomorrow? |  |
| qwen3-0.6b+guard | Uh, what's the weather tomorrow? |  |
| qwen3-0.6b@rules | What's the weather tomorrow? |  |
| qwen3-0.6b+guard@rules | What's the weather tomorrow? |  |
| rules+ | What's the weather tomorrow? |  |
| rules+@kroko+rules | Ah, him what's the weather tomorrow? | MEANING +ah |
| rules+@kroko | Ah, him what's the weather tomorrow? | MEANING +ah |
| rules-seam | What's the weather tomorrow |  |
| rules-seam@kroko | Ah, him what's the weather tomorrow? | MEANING +ah |
| t5-base | uh hmm, what's the weather tomorrow? |  |
| t5-base+guard | Uh hmm, what's the weather tomorrow? |  |
| t5-base@kroko+rules | Ah, he, what's the weather tomorrow? | MEANING +ah |
| t5-base+guard@kroko+rules | Ah, him what's the weather tomorrow? | MEANING +ah |
| t5-base@rules | What's the weather tomorrow? |  |
| t5-base+guard@rules | What's the weather tomorrow? |  |
| t5-mini | Oh hmm, what the weather is tomorrow? | MEANING +oh, +what, -what's |
| t5-mini+guard | Uh hmm, what's the weather tomorrow? |  |
| t5-mini@rules#t2 | What is the weather tomorrow? | MEANING +what, -what's |
| t5-mini+guard@rules#t2 | What's the weather tomorrow? |  |
| t5-mini@rules | What is the weather tomorrow? | MEANING +what, -what's |
| t5-mini+guard@rules | What's the weather tomorrow? |  |
| t5-small-gec | Uh hmm, what's the weather tomorrow? |  |
| t5-small-gec+guard | Uh hmm, what's the weather tomorrow? |  |
| t5-small-gec@kroko+rules | Ah, him, what's the weather like tomorrow? | MEANING +ah, +like |
| t5-small-gec+guard@kroko+rules | Ah, him, what's the weather tomorrow? | MEANING +ah |
| t5-small-gec@rules#t2 | What's the weather like tomorrow? | MEANING +like |
| t5-small-gec+guard@rules#t2 | What's the weather tomorrow? |  |
| t5-small-gec@rules | What's the weather like tomorrow? | MEANING +like |
| t5-small-gec+guard@rules | What's the weather tomorrow? |  |
| t5-small-synth | Oh wow! What is the weather tomorrow? | MEANING +oh, +what, +wow, -what's |
| t5-small-synth+guard | Uh hmm what's the weather tomorrow? |  |
| t5-small-synth@rules | What's the weather tomorrow? |  |
| t5-small-synth+guard@rules | What's the weather tomorrow? |  |
| t5-tiny+guard>punct-en+guard@rules | What's the weather tomorrow? |  |
| t5-tiny | Oh hmm, what the weather tomorrow? | MEANING +oh, +what, -what's |
| t5-tiny+guard | Uh hmm, what's the weather tomorrow? |  |
| t5-tiny@kroko+rules | Ah, what is the weather tomorrow? | MEANING +ah, +what, -what's |
| t5-tiny+guard@kroko+rules | Ah, him what's the weather tomorrow? | MEANING +ah |
| t5-tiny@rules#t2 | What the weather tomorrow? | MEANING +what, -what's |
| t5-tiny+guard@rules#t2 | What's the weather tomorrow? |  |
| t5-tiny@rules | What the weather tomorrow? | MEANING +what, -what's |
| t5-tiny+guard@rules | What's the weather tomorrow? |  |

### f04 (fillers)

| option | output | flag |
|---|---|---|
| ref | Remind me to call Mom at six. |  |
| (raw words, untouched) | er remind me to call mom at six |  |
| asr-kroko | Er remind me to call Mom at six. |  |
| asr-moonshine-base | Or remind me to call mom at 6 | MEANING +6, -six, lost 'six', numbers differ |
| asr-moonshine-tiny | "Ell remind me to call mom at 6. | MEANING +6, +ell, -six, lost 'six', numbers differ |
| lfm2.5-1.2b | Remind me to call mom at six. |  |
| lfm2.5-1.2b+guard | Remind me to call mom at six. |  |
| lfm2.5-1.2b@rules | Remind me to call mom at six |  |
| lfm2.5-1.2b+guard@rules | Remind me to call mom at six. |  |
| punct-ct+guard@rules | Remind me to call mom at six. |  |
| punct-ct | er remind me to call mom at six。 |  |
| punct-en+guard>t5-small-gec+guard@rules | Remind me to call Mom at six. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Remind me to call Mom at six. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | Remind me to call Mom at six. |  |
| punct-en+guard>t5-tiny+guard@rules | Remind me to call Mom at six. |  |
| punct-en+guard@kroko+rules | Remind me to call Mom at six. |  |
| punct-en+guard@rules#t2 | Remind me to call Mom at six. |  |
| punct-en+guard@rules | Remind me to call Mom at six. |  |
| punct-en | Er remind me to call Mom at six |  |
| qwen2.5-0.5b | Er, remind me to call mom at six. |  |
| qwen2.5-0.5b+guard | Er, remind me to call mom at six. |  |
| qwen2.5-0.5b@kroko+rules | Remind me to call Mom at six. |  |
| qwen2.5-0.5b+guard@kroko+rules | Remind me to call Mom at six. |  |
| qwen2.5-0.5b@rules#t2 | Remind me to call mom at six. |  |
| qwen2.5-0.5b+guard@rules#t2 | Remind me to call mom at six. |  |
| qwen2.5-0.5b@rules | Remind me to call mom at six. |  |
| qwen2.5-0.5b+guard@rules | Remind me to call mom at six. |  |
| qwen3-0.6b | Er, remind me to call mom at six. |  |
| qwen3-0.6b+guard | Er, remind me to call mom at six. |  |
| qwen3-0.6b@rules | Remind me to call mom at six. |  |
| qwen3-0.6b+guard@rules | Remind me to call mom at six. |  |
| rules+ | Remind me to call mom at six. |  |
| rules+@kroko+rules | Remind me to call Mom at six. |  |
| rules+@kroko | Remind me to call Mom at six. |  |
| rules-seam | Remind me to call mom at six |  |
| rules-seam@kroko | Remind me to call Mom at six. |  |
| t5-base | Er remind me to call mom at six. |  |
| t5-base+guard | Er remind me to call mom at six. |  |
| t5-base@kroko+rules | Remind me to call Mom at six. |  |
| t5-base+guard@kroko+rules | Remind me to call Mom at six. |  |
| t5-base@rules | Remind me to call mom at six. |  |
| t5-base+guard@rules | Remind me to call mom at six. |  |
| t5-mini | Here reminds me to call mom at six. | MEANING +here, +reminds, -remind |
| t5-mini+guard | Er remind me to call mom at six. |  |
| t5-mini@rules#t2 | I remind myself to call mom at six. | MEANING +myself |
| t5-mini+guard@rules#t2 | Remind me to call mom at six. |  |
| t5-mini@rules | I remind myself to call mom at six. | MEANING +myself |
| t5-mini+guard@rules | Remind me to call mom at six. |  |
| t5-small-gec | Er reminds me to call mom at six. | MEANING +reminds, -remind |
| t5-small-gec+guard | Er remind me to call mom at six. |  |
| t5-small-gec@kroko+rules | Remind me to call Mom at six. |  |
| t5-small-gec+guard@kroko+rules | Remind me to call Mom at six. |  |
| t5-small-gec@rules#t2 | Remind me to call mom at six |  |
| t5-small-gec+guard@rules#t2 | Remind me to call mom at six. |  |
| t5-small-gec@rules | Remind me to call mom at six |  |
| t5-small-gec+guard@rules | Remind me to call mom at six. |  |
| t5-small-synth | erroneously, I can call her at jones. | MEANING +erroneously, +jones, -mom, -remind, -six, lost 'six', numbers differ |
| t5-small-synth+guard | Er remind me to call mom at six. |  |
| t5-small-synth@rules | Redhead calls me at 9:30 am. | MEANING +9:30, +calls, +redhead, -call, -mom, -remind, -six, lost 'call', lost 'six', numbers differ |
| t5-small-synth+guard@rules | Remind me to call mom at six. |  |
| t5-tiny+guard>punct-en+guard@rules | Remind me to call Mom at six. |  |
| t5-tiny | Here reminds me to call mom at six. | MEANING +here, +reminds, -remind |
| t5-tiny+guard | Er remind me to call mom at six. |  |
| t5-tiny@kroko+rules | I remind me to call Mom at six. | reworded +i |
| t5-tiny+guard@kroko+rules | Remind me to call Mom at six. |  |
| t5-tiny@rules#t2 | I remind me to call mom at six. | reworded +i |
| t5-tiny+guard@rules#t2 | Remind me to call mom at six. |  |
| t5-tiny@rules | I remind me to call mom at six. | reworded +i |
| t5-tiny+guard@rules | Remind me to call mom at six. |  |

### f05 (fillers)

| option | output | flag |
|---|---|---|
| ref | I like the second one better, the blue one. |  |
| (raw words, untouched) | i like the second one better um the blue one |  |
| asr-kroko | I like the second one bedroom, the blue one | MEANING +bedroom, -better |
| asr-moonshine-base | I like the second one better on the blue one | reworded +on |
| asr-moonshine-tiny | I like the second one better um the blue one |  |
| lfm2.5-1.2b | I like the second one better, the blue one. |  |
| lfm2.5-1.2b+guard | I like the second one better, the blue one. |  |
| lfm2.5-1.2b@rules | I like the second one better the blue one. |  |
| lfm2.5-1.2b+guard@rules | I like the second one better the blue one. |  |
| punct-ct+guard@rules | I like the second one, better the blue one. |  |
| punct-ct | i like the second one better um the blue one。 |  |
| punct-en+guard>t5-small-gec+guard@rules | I like the second one better, the blue one. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | I like the second one, bedroom, the blue one. | MEANING +bedroom, -better |
| punct-en+guard>t5-tiny+guard@rules#t2 | I like the second one, better, the blue one. |  |
| punct-en+guard>t5-tiny+guard@rules | I like the second one, better, the blue one. |  |
| punct-en+guard@kroko+rules | I, like the second one bedroom, the blue one. | MEANING +bedroom, -better |
| punct-en+guard@rules#t2 | I like the second one better, the blue one. |  |
| punct-en+guard@rules | I like the second one better, the blue one. |  |
| punct-en | I like the second one better. UM, the blue one |  |
| qwen2.5-0.5b | I like the second one better, the blue one. |  |
| qwen2.5-0.5b+guard | I like the second one better, the blue one. |  |
| qwen2.5-0.5b@kroko+rules | I like the second one bedroom, the blue one. | MEANING +bedroom, -better |
| qwen2.5-0.5b+guard@kroko+rules | I like the second one bedroom, the blue one. | MEANING +bedroom, -better |
| qwen2.5-0.5b@rules#t2 | I like the second one better, the blue one. |  |
| qwen2.5-0.5b+guard@rules#t2 | I like the second one better, the blue one. |  |
| qwen2.5-0.5b@rules | I like the second one better, the blue one. |  |
| qwen2.5-0.5b+guard@rules | I like the second one better, the blue one. |  |
| qwen3-0.6b | I like the second one better, um the blue one. |  |
| qwen3-0.6b+guard | I like the second one better, um the blue one. |  |
| qwen3-0.6b@rules | I like the second one better, the blue one. |  |
| qwen3-0.6b+guard@rules | I like the second one better, the blue one. |  |
| rules+ | I like the second one better the blue one. |  |
| rules+@kroko+rules | I like the second one bedroom, the blue one. | MEANING +bedroom, -better |
| rules+@kroko | I like the second one bedroom, the blue one. | MEANING +bedroom, -better |
| rules-seam | I like the second one better the blue one |  |
| rules-seam@kroko | I like the second one bedroom, the blue one | MEANING +bedroom, -better |
| t5-base | I like the second one better than the blue one. | reworded +than |
| t5-base+guard | I like the second one better um the blue one. |  |
| t5-base@kroko+rules | I like the second one bedroom, the blue one. | MEANING +bedroom, -better |
| t5-base+guard@kroko+rules | I like the second one bedroom, the blue one. | MEANING +bedroom, -better |
| t5-base@rules | I like the second one better the blue one. |  |
| t5-base+guard@rules | I like the second one better the blue one. |  |
| t5-mini | I like the second one better and the blue one. | reworded +and |
| t5-mini+guard | I like the second one better um the blue one. |  |
| t5-mini@rules#t2 | I like the second one better than the blue one. | reworded +than |
| t5-mini+guard@rules#t2 | I like the second one better the blue one. |  |
| t5-mini@rules | I like the second one better than the blue one. | reworded +than |
| t5-mini+guard@rules | I like the second one better the blue one. |  |
| t5-small-gec | I like the second one better than the blue one. | reworded +than |
| t5-small-gec+guard | I like the second one better um the blue one. |  |
| t5-small-gec@kroko+rules | I like the second one bedroom, the blue one. | MEANING +bedroom, -better |
| t5-small-gec+guard@kroko+rules | I like the second one bedroom, the blue one. | MEANING +bedroom, -better |
| t5-small-gec@rules#t2 | I like the second one better than the blue one. | reworded +than |
| t5-small-gec+guard@rules#t2 | I like the second one better the blue one. |  |
| t5-small-gec@rules | I like the second one better than the blue one. | reworded +than |
| t5-small-gec+guard@rules | I like the second one better the blue one. |  |
| t5-small-synth | I like the second one better than the third one. | MEANING +third, -blue, lost 'blue' |
| t5-small-synth+guard | I like the second one better um the blue one. |  |
| t5-small-synth@rules | I like the second one better than the blue one. | reworded +than |
| t5-small-synth+guard@rules | I like the second one better the blue one. |  |
| t5-tiny+guard>punct-en+guard@rules | I like the second one, better, the Blue One. |  |
| t5-tiny | I like the second one better and the blue one. | reworded +and |
| t5-tiny+guard | I like the second one better um the blue one. |  |
| t5-tiny@kroko+rules | I like the second one bedroom, the blue one. | MEANING +bedroom, -better |
| t5-tiny+guard@kroko+rules | I like the second one bedroom, the blue one. | MEANING +bedroom, -better |
| t5-tiny@rules#t2 | I like the second one, the better blue one. | reworded -the |
| t5-tiny+guard@rules#t2 | I like the second one, better the blue one. |  |
| t5-tiny@rules | I like the second one, the better blue one. | reworded -the |
| t5-tiny+guard@rules | I like the second one, better the blue one. |  |

### f06 (fillers)

| option | output | flag |
|---|---|---|
| ref | It was like twenty minutes late. |  |
| (raw words, untouched) | it was like twenty minutes late |  |
| asr-kroko | It was like twenty minutes late |  |
| asr-moonshine-base | It was like 20 minutes late | MEANING +20, -twenty, lost 'twenty', numbers differ |
| asr-moonshine-tiny | It was like 20 minutes late. | MEANING +20, -twenty, lost 'twenty', numbers differ |
| lfm2.5-1.2b | It was like twenty minutes late. |  |
| lfm2.5-1.2b+guard | It was like twenty minutes late. |  |
| lfm2.5-1.2b@rules | It was like twenty minutes late. |  |
| lfm2.5-1.2b+guard@rules | It was like twenty minutes late. |  |
| punct-ct+guard@rules | It was like twenty minutes late. |  |
| punct-ct | it was like twenty minutes late。 |  |
| punct-en+guard>t5-small-gec+guard@rules | It was like twenty minutes late. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | It was like twenty minutes late. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | It was like twenty minutes late. |  |
| punct-en+guard>t5-tiny+guard@rules | It was like twenty minutes late. |  |
| punct-en+guard@kroko+rules | It was like twenty minutes late. |  |
| punct-en+guard@rules#t2 | It was like twenty minutes late. |  |
| punct-en+guard@rules | It was like twenty minutes late. |  |
| punct-en | It was like twenty minutes late |  |
| qwen2.5-0.5b | It was like twenty minutes late. |  |
| qwen2.5-0.5b+guard | It was like twenty minutes late. |  |
| qwen2.5-0.5b@kroko+rules | It was like twenty minutes late. |  |
| qwen2.5-0.5b+guard@kroko+rules | It was like twenty minutes late. |  |
| qwen2.5-0.5b@rules#t2 | It was like twenty minutes late. |  |
| qwen2.5-0.5b+guard@rules#t2 | It was like twenty minutes late. |  |
| qwen2.5-0.5b@rules | It was like twenty minutes late. |  |
| qwen2.5-0.5b+guard@rules | It was like twenty minutes late. |  |
| qwen3-0.6b | It was like twenty minutes late. |  |
| qwen3-0.6b+guard | It was like twenty minutes late. |  |
| qwen3-0.6b@rules | It was like twenty minutes late. |  |
| qwen3-0.6b+guard@rules | It was like twenty minutes late. |  |
| rules+ | It was like twenty minutes late. |  |
| rules+@kroko+rules | It was like twenty minutes late. |  |
| rules+@kroko | It was like twenty minutes late. |  |
| rules-seam | It was like twenty minutes late |  |
| rules-seam@kroko | It was like twenty minutes late |  |
| t5-base | It was like twenty minutes late. |  |
| t5-base+guard | It was like twenty minutes late. |  |
| t5-base@kroko+rules | It was like twenty minutes late. |  |
| t5-base+guard@kroko+rules | It was like twenty minutes late. |  |
| t5-base@rules | It was like twenty minutes late. |  |
| t5-base+guard@rules | It was like twenty minutes late. |  |
| t5-mini | It was like twenty minutes late. |  |
| t5-mini+guard | It was like twenty minutes late. |  |
| t5-mini@rules#t2 | It was like twenty minutes late. |  |
| t5-mini+guard@rules#t2 | It was like twenty minutes late. |  |
| t5-mini@rules | It was like twenty minutes late. |  |
| t5-mini+guard@rules | It was like twenty minutes late. |  |
| t5-small-gec | it was like twenty minutes late |  |
| t5-small-gec+guard | It was like twenty minutes late. |  |
| t5-small-gec@kroko+rules | It was like twenty minutes late. |  |
| t5-small-gec+guard@kroko+rules | It was like twenty minutes late. |  |
| t5-small-gec@rules#t2 | It was like twenty minutes late. |  |
| t5-small-gec+guard@rules#t2 | It was like twenty minutes late. |  |
| t5-small-gec@rules | It was like twenty minutes late. |  |
| t5-small-gec+guard@rules | It was like twenty minutes late. |  |
| t5-small-synth | It was like twenty minutes since then. | MEANING +since, -late |
| t5-small-synth+guard | It was like twenty minutes late. |  |
| t5-small-synth@rules | It was like twenty minutes late. |  |
| t5-small-synth+guard@rules | It was like twenty minutes late. |  |
| t5-tiny+guard>punct-en+guard@rules | It was like twenty minutes, late. |  |
| t5-tiny | It was like twenty minutes late. |  |
| t5-tiny+guard | It was like twenty minutes late. |  |
| t5-tiny@kroko+rules | It was like twenty minutes late. |  |
| t5-tiny+guard@kroko+rules | It was like twenty minutes late. |  |
| t5-tiny@rules#t2 | It was like twenty minutes late. |  |
| t5-tiny+guard@rules#t2 | It was like twenty minutes late. |  |
| t5-tiny@rules | It was like twenty minutes late. |  |
| t5-tiny+guard@rules | It was like twenty minutes late. |  |

### s01 (stutter)

| option | output | flag |
|---|---|---|
| ref | I want to send a message to Priya. |  |
| (raw words, untouched) | i i i want to send a message to to priya |  |
| asr-kroko | I want to send a message to Depriya. | MEANING +depriya, -priya, lost 'Priya' |
| asr-moonshine-base | I I I want to send a message to the Priya | reworded +the |
| asr-moonshine-tiny | I i i want to send a message to the Priya | reworded +the |
| lfm2.5-1.2b | I want to send a message to Priya. |  |
| lfm2.5-1.2b+guard | I want to send a message to Priya. |  |
| lfm2.5-1.2b@rules | I want to send a message to Priya |  |
| lfm2.5-1.2b+guard@rules | I want to send a message to Priya. |  |
| punct-ct+guard@rules | I want to send a message to priya. |  |
| punct-ct | i i i want to send a message to to priya。 |  |
| punct-en+guard>t5-small-gec+guard@rules | I want to send a message to Priya. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | I want to send a message to Depriya. | MEANING +depriya, -priya, lost 'Priya' |
| punct-en+guard>t5-tiny+guard@rules#t2 | I want to send a message to Priya. |  |
| punct-en+guard>t5-tiny+guard@rules | I want to send a message to Priya. |  |
| punct-en+guard@kroko+rules | I want to send a message to Depriya. | MEANING +depriya, -priya, lost 'Priya' |
| punct-en+guard@rules#t2 | I want to send a message to Priya. |  |
| punct-en+guard@rules | I want to send a message to Priya. |  |
| punct-en | I, I, I want to send a message to to Priya |  |
| qwen2.5-0.5b | I I want to send a message to Priya. |  |
| qwen2.5-0.5b+guard | I I want to send a message to Priya. |  |
| qwen2.5-0.5b@kroko+rules | I want to send a message to Depriya. | MEANING +depriya, -priya, lost 'Priya' |
| qwen2.5-0.5b+guard@kroko+rules | I want to send a message to Depriya. | MEANING +depriya, -priya, lost 'Priya' |
| qwen2.5-0.5b@rules#t2 | I want to send a message to Priya. |  |
| qwen2.5-0.5b+guard@rules#t2 | I want to send a message to Priya. |  |
| qwen2.5-0.5b@rules | I want to send a message to Priya. |  |
| qwen2.5-0.5b+guard@rules | I want to send a message to Priya. |  |
| qwen3-0.6b | I want to send a message to Priya. |  |
| qwen3-0.6b+guard | I want to send a message to Priya. |  |
| qwen3-0.6b@rules | I want to send a message to Priya. |  |
| qwen3-0.6b+guard@rules | I want to send a message to Priya. |  |
| rules+ | I want to send a message to priya. |  |
| rules+@kroko+rules | I want to send a message to Depriya. | MEANING +depriya, -priya, lost 'Priya' |
| rules+@kroko | I want to send a message to Depriya. | MEANING +depriya, -priya, lost 'Priya' |
| rules-seam | I want to send a message to priya |  |
| rules-seam@kroko | I want to send a message to Depriya. | MEANING +depriya, -priya, lost 'Priya' |
| t5-base | I want to send a message to priya. |  |
| t5-base+guard | I want to send a message to priya. |  |
| t5-base@kroko+rules | I want to send a message to Depriya. | MEANING +depriya, -priya, lost 'Priya' |
| t5-base+guard@kroko+rules | I want to send a message to Depriya. | MEANING +depriya, -priya, lost 'Priya' |
| t5-base@rules | I want to send a message to priya. |  |
| t5-base+guard@rules | I want to send a message to priya. |  |
| t5-mini | I think I want to send a message to a priya. | MEANING +think |
| t5-mini+guard | I i I want to send a message to to priya. |  |
| t5-mini@rules#t2 | I want to send a message to a priya. |  |
| t5-mini+guard@rules#t2 | I want to send a message to priya. |  |
| t5-mini@rules | I want to send a message to a priya. |  |
| t5-mini+guard@rules | I want to send a message to priya. |  |
| t5-small-gec | I want to send a message to priya. |  |
| t5-small-gec+guard | I want to send a message to priya. |  |
| t5-small-gec@kroko+rules | I want to send a message to Depriya. | MEANING +depriya, -priya, lost 'Priya' |
| t5-small-gec+guard@kroko+rules | I want to send a message to Depriya. | MEANING +depriya, -priya, lost 'Priya' |
| t5-small-gec@rules#t2 | I want to send a message to priya |  |
| t5-small-gec+guard@rules#t2 | I want to send a message to priya. |  |
| t5-small-gec@rules | I want to send a message to priya |  |
| t5-small-gec+guard@rules | I want to send a message to priya. |  |
| t5-small-synth | I want to send a message to my parents to help with homework. | MEANING +help, +homework, +parents, -priya, lost 'Priya' |
| t5-small-synth+guard | I want to send a message to to priya. |  |
| t5-small-synth@rules | I want to send a message to a person interested in politics. | MEANING +interested, +person, +politics, -priya, lost 'Priya' |
| t5-small-synth+guard@rules | I want to send a message to priya. |  |
| t5-tiny+guard>punct-en+guard@rules | I want to send a message to priya. |  |
| t5-tiny | I think I want to send a message to a party. | MEANING +party, +think, -priya, lost 'Priya' |
| t5-tiny+guard | I i I want to send a message to to priya. |  |
| t5-tiny@kroko+rules | I want to send a message to Depriya. | MEANING +depriya, -priya, lost 'Priya' |
| t5-tiny+guard@kroko+rules | I want to send a message to Depriya. | MEANING +depriya, -priya, lost 'Priya' |
| t5-tiny@rules#t2 | I want to send a message to the party. | MEANING +party, -priya, lost 'Priya' |
| t5-tiny+guard@rules#t2 | I want to send a message to priya. |  |
| t5-tiny@rules | I want to send a message to the party. | MEANING +party, -priya, lost 'Priya' |
| t5-tiny+guard@rules | I want to send a message to priya. |  |

### s02 (stutter)

| option | output | flag |
|---|---|---|
| ref | Can you turn the volume down? |  |
| (raw words, untouched) | can you can you turn the volume down |  |
| asr-kroko | Can you turn the volume down |  |
| asr-moonshine-base | Can you can you turn the volume down? |  |
| asr-moonshine-tiny | Can you can you turn the volume down? |  |
| lfm2.5-1.2b | Can you turn the volume down? |  |
| lfm2.5-1.2b+guard | Can you Can you turn the volume down? |  |
| lfm2.5-1.2b@rules | Can you turn the volume down? |  |
| lfm2.5-1.2b+guard@rules | Can you turn the volume down? |  |
| punct-ct+guard@rules | Can you turn the volume down? |  |
| punct-ct | can you can you turn the volume down？ |  |
| punct-en+guard>t5-small-gec+guard@rules | Can you turn the volume down? |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Can you turn the volume down? |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | Can you turn the volume down? |  |
| punct-en+guard>t5-tiny+guard@rules | Can you turn the volume down? |  |
| punct-en+guard@kroko+rules | Can you turn the volume down? |  |
| punct-en+guard@rules#t2 | Can you turn the volume down? |  |
| punct-en+guard@rules | Can you turn the volume down? |  |
| punct-en | Can you can you turn the volume down |  |
| qwen2.5-0.5b | Can you turn the volume down? |  |
| qwen2.5-0.5b+guard | Can you Can you turn the volume down? |  |
| qwen2.5-0.5b@kroko+rules | Can you turn the volume down? |  |
| qwen2.5-0.5b+guard@kroko+rules | Can you turn the volume down? |  |
| qwen2.5-0.5b@rules#t2 | Can you turn the volume down? |  |
| qwen2.5-0.5b+guard@rules#t2 | Can you turn the volume down? |  |
| qwen2.5-0.5b@rules | Can you turn the volume down? |  |
| qwen2.5-0.5b+guard@rules | Can you turn the volume down? |  |
| qwen3-0.6b | Can you turn the volume down? |  |
| qwen3-0.6b+guard | Can you Can you turn the volume down? |  |
| qwen3-0.6b@rules | Can you turn the volume down? |  |
| qwen3-0.6b+guard@rules | Can you turn the volume down? |  |
| rules+ | Can you turn the volume down? |  |
| rules+@kroko+rules | Can you turn the volume down? |  |
| rules+@kroko | Can you turn the volume down? |  |
| rules-seam | Can you turn the volume down |  |
| rules-seam@kroko | Can you turn the volume down |  |
| t5-base | Can you turn the volume down? Can you turn the volume down? |  |
| t5-base+guard | Can you Can you turn the volume down? |  |
| t5-base@kroko+rules | Can you turn the volume down? |  |
| t5-base+guard@kroko+rules | Can you turn the volume down? |  |
| t5-base@rules | Can you turn the volume down? |  |
| t5-base+guard@rules | Can you turn the volume down? |  |
| t5-mini | Can you can turn the volume down? |  |
| t5-mini+guard | Can you can you turn the volume down? |  |
| t5-mini@rules#t2 | You can turn the volume down. | reworded -you |
| t5-mini+guard@rules#t2 | Can you turn the volume down. |  |
| t5-mini@rules | You can turn the volume down. | reworded -you |
| t5-mini+guard@rules | Can you turn the volume down. |  |
| t5-small-gec | Can you can you turn the volume down? |  |
| t5-small-gec+guard | Can you can you turn the volume down? |  |
| t5-small-gec@kroko+rules | Can you turn the volume down? |  |
| t5-small-gec+guard@kroko+rules | Can you turn the volume down? |  |
| t5-small-gec@rules#t2 | Can you turn the volume down? |  |
| t5-small-gec+guard@rules#t2 | Can you turn the volume down? |  |
| t5-small-gec@rules | Can you turn the volume down? |  |
| t5-small-gec+guard@rules | Can you turn the volume down? |  |
| t5-small-synth | can you turn the volume down? |  |
| t5-small-synth+guard | Can you can you turn the volume down? |  |
| t5-small-synth@rules | Can you turn the volume down? |  |
| t5-small-synth+guard@rules | Can you turn the volume down? |  |
| t5-tiny+guard>punct-en+guard@rules | Can you turn the volume down? |  |
| t5-tiny | Can you turn the volume down? |  |
| t5-tiny+guard | Can you Can you turn the volume down? |  |
| t5-tiny@kroko+rules | Can you turn the volume down? |  |
| t5-tiny+guard@kroko+rules | Can you turn the volume down? |  |
| t5-tiny@rules#t2 | Can you turn the volume down? |  |
| t5-tiny+guard@rules#t2 | Can you turn the volume down? |  |
| t5-tiny@rules | Can you turn the volume down? |  |
| t5-tiny+guard@rules | Can you turn the volume down? |  |

### s03 (stutter)

| option | output | flag |
|---|---|---|
| ref | This is very very important, please read it. |  |
| (raw words, untouched) | this is very very important please read it |  |
| asr-kroko | This is very, very important please, read it |  |
| asr-moonshine-base | This is very very important please read it |  |
| asr-moonshine-tiny | This is very very important please read it |  |
| lfm2.5-1.2b | This is very very important please read it |  |
| lfm2.5-1.2b+guard | This is very very important please read it. |  |
| lfm2.5-1.2b@rules | This is really very very important please read it | MEANING +really |
| lfm2.5-1.2b+guard@rules | This is very very important please read it. |  |
| punct-ct+guard@rules | This is very, very important, please read it. |  |
| punct-ct | this is very，very important，please read it。 | MEANING +important，please, +very，very, -important, -please, -very, lost 'very very' |
| punct-en+guard>t5-small-gec+guard@rules | This is very, very important. Please read it. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | This is very, very important. Please, read it. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | This is very, very important. Please read it. |  |
| punct-en+guard>t5-tiny+guard@rules | This is very, very important. Please read it. |  |
| punct-en+guard@kroko+rules | This is very, very important. Please, read it. |  |
| punct-en+guard@rules#t2 | This is very, very important. Please read it. |  |
| punct-en+guard@rules | This is very, very important. Please read it. |  |
| punct-en | This is very, very important. Please read it. |  |
| qwen2.5-0.5b | This is very very important, please read it. |  |
| qwen2.5-0.5b+guard | This is very very important, please read it. |  |
| qwen2.5-0.5b@kroko+rules | This is very, very important, please, read it. |  |
| qwen2.5-0.5b+guard@kroko+rules | This is very, very important, please, read it. |  |
| qwen2.5-0.5b@rules#t2 | This is very very important, please read it. |  |
| qwen2.5-0.5b+guard@rules#t2 | This is very very important, please read it. |  |
| qwen2.5-0.5b@rules | This is very very important, please read it. |  |
| qwen2.5-0.5b+guard@rules | This is very very important, please read it. |  |
| qwen3-0.6b | This is very important, please read it. | MEANING -very, lost 'very very' |
| qwen3-0.6b+guard | This is very very important, please read it. |  |
| qwen3-0.6b@rules | This is very important please read it. | MEANING -very, lost 'very very' |
| qwen3-0.6b+guard@rules | This is very very important please read it. |  |
| rules+ | This is very very important please read it. |  |
| rules+@kroko+rules | This is very, very important please, read it. |  |
| rules+@kroko | This is very, very important please, read it. |  |
| rules-seam | This is very very important please read it |  |
| rules-seam@kroko | This is very, very important please, read it |  |
| t5-base | This is very important, please read it. | MEANING -very, lost 'very very' |
| t5-base+guard | This is very very important, please read it. |  |
| t5-base@kroko+rules | This is very, very important, please, read it. |  |
| t5-base+guard@kroko+rules | This is very, very important, please, read it. |  |
| t5-base@rules | This is very important, please read it. | MEANING -very, lost 'very very' |
| t5-base+guard@rules | This is very very important, please read it. |  |
| t5-mini | This is very very important, please read it. |  |
| t5-mini+guard | This is very very important, please read it. |  |
| t5-mini@rules#t2 | This is very very important, please read it. |  |
| t5-mini+guard@rules#t2 | This is very very important, please read it. |  |
| t5-mini@rules | This is very very important, please read it. |  |
| t5-mini+guard@rules | This is very very important, please read it. |  |
| t5-small-gec | This is very very important. Please read it. |  |
| t5-small-gec+guard | This is very very important. Please read it. |  |
| t5-small-gec@kroko+rules | This is very, very important. Please, read it. |  |
| t5-small-gec+guard@kroko+rules | This is very, very important. Please, read it. |  |
| t5-small-gec@rules#t2 | This is very very important. Please read it. |  |
| t5-small-gec+guard@rules#t2 | This is very very important. Please read it. |  |
| t5-small-gec@rules | This is very very important. Please read it. |  |
| t5-small-gec+guard@rules | This is very very important. Please read it. |  |
| t5-small-synth | this is very important to read it. | MEANING -please, -very, lost 'very very' |
| t5-small-synth+guard | This is very very important please read it. |  |
| t5-small-synth@rules | This is very important to read it. | MEANING -please, -very, lost 'very very' |
| t5-small-synth+guard@rules | This is very very important please read it. |  |
| t5-tiny+guard>punct-en+guard@rules | This is very, very important. Please read it. |  |
| t5-tiny | This is very very important, please read it. |  |
| t5-tiny+guard | This is very very important, please read it. |  |
| t5-tiny@kroko+rules | This is very, very important, please read it. |  |
| t5-tiny+guard@kroko+rules | This is very, very important, please read it. |  |
| t5-tiny@rules#t2 | This is very very important, please read it. |  |
| t5-tiny+guard@rules#t2 | This is very very important, please read it. |  |
| t5-tiny@rules | This is very very important, please read it. |  |
| t5-tiny+guard@rules | This is very very important, please read it. |  |

### s04 (stutter)

| option | output | flag |
|---|---|---|
| ref | No, no, don't delete that file. |  |
| (raw words, untouched) | no no don't delete that file |  |
| asr-kroko | No, no don't delete that file |  |
| asr-moonshine-base | No, no, don't delete that file. |  |
| asr-moonshine-tiny | No, no, don't delete that file. |  |
| lfm2.5-1.2b | No, don't delete that file | MEANING -no, negation differs |
| lfm2.5-1.2b+guard | No No, don't delete that file. |  |
| lfm2.5-1.2b@rules | No, don't delete that file | MEANING -no, negation differs |
| lfm2.5-1.2b+guard@rules | No No, don't delete that file. |  |
| punct-ct+guard@rules | No, no, don't delete that file. |  |
| punct-ct | no，no，don't delete that file。 | MEANING +no，no，don't, -don't, -no |
| punct-en+guard>t5-small-gec+guard@rules | No, no, don't delete that file. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | No, no, don't delete that file. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | No, no, don't delete that file. |  |
| punct-en+guard>t5-tiny+guard@rules | No, no, don't delete that file. |  |
| punct-en+guard@kroko+rules | No, no, don't delete that file. |  |
| punct-en+guard@rules#t2 | No, no don't delete that file. |  |
| punct-en+guard@rules | No, no don't delete that file. |  |
| punct-en | No, no don't delete that file |  |
| qwen2.5-0.5b | No, don't delete that file. | MEANING -no, negation differs |
| qwen2.5-0.5b+guard | No No, don't delete that file. |  |
| qwen2.5-0.5b@kroko+rules | No, no don't delete that file. |  |
| qwen2.5-0.5b+guard@kroko+rules | No, no don't delete that file. |  |
| qwen2.5-0.5b@rules#t2 | No, don't delete that file. | MEANING -no, negation differs |
| qwen2.5-0.5b+guard@rules#t2 | No No, don't delete that file. |  |
| qwen2.5-0.5b@rules | No, don't delete that file. | MEANING -no, negation differs |
| qwen2.5-0.5b+guard@rules | No No, don't delete that file. |  |
| qwen3-0.6b | No no, don't delete that file. |  |
| qwen3-0.6b+guard | No no, don't delete that file. |  |
| qwen3-0.6b@rules | No no, don't delete that file. |  |
| qwen3-0.6b+guard@rules | No no, don't delete that file. |  |
| rules+ | No no don't delete that file. |  |
| rules+@kroko+rules | No, no don't delete that file. |  |
| rules+@kroko | No, no don't delete that file. |  |
| rules-seam | No no don't delete that file |  |
| rules-seam@kroko | No, no don't delete that file |  |
| t5-base | No, don't delete that file. | MEANING -no, negation differs |
| t5-base+guard | No No, don't delete that file. |  |
| t5-base@kroko+rules | No, don't delete that file. | MEANING -no, negation differs |
| t5-base+guard@kroko+rules | No, No, don't delete that file. |  |
| t5-base@rules | No, don't delete that file. | MEANING -no, negation differs |
| t5-base+guard@rules | No No, don't delete that file. |  |
| t5-mini | No, no, no delete that file. | MEANING -don't, lost 'don't', negation differs |
| t5-mini+guard | No, no, don't delete that file. |  |
| t5-mini@rules#t2 | No, no, no delete that file. | MEANING -don't, lost 'don't', negation differs |
| t5-mini+guard@rules#t2 | No, no, don't delete that file. |  |
| t5-mini@rules | No, no, no delete that file. | MEANING -don't, lost 'don't', negation differs |
| t5-mini+guard@rules | No, no, don't delete that file. |  |
| t5-small-gec | No no, don't delete that file. |  |
| t5-small-gec+guard | No no, don't delete that file. |  |
| t5-small-gec@kroko+rules | No, no, don't delete that file. |  |
| t5-small-gec+guard@kroko+rules | No, no, don't delete that file. |  |
| t5-small-gec@rules#t2 | No no, don't delete that file. |  |
| t5-small-gec+guard@rules#t2 | No no, don't delete that file. |  |
| t5-small-gec@rules | No no, don't delete that file. |  |
| t5-small-gec+guard@rules | No no, don't delete that file. |  |
| t5-small-synth | no no no no no no no no no no no no no no no no no no no no no no no no no no | MEANING -delete, -don't, -file, lost 'delete', lost 'don't', negation differs |
| t5-small-synth+guard | No no don't delete that file. |  |
| t5-small-synth@rules | No no no no no no no no no no no no no no no no no no no no no no no no no no | MEANING -delete, -don't, -file, lost 'delete', lost 'don't', negation differs |
| t5-small-synth+guard@rules | No no don't delete that file. |  |
| t5-tiny+guard>punct-en+guard@rules | No, no, don't delete that file. |  |
| t5-tiny | No, no, no, no delete that file | MEANING -don't, lost 'don't', negation differs |
| t5-tiny+guard | No, no, don't delete that file. |  |
| t5-tiny@kroko+rules | No, no one deletes that file. | MEANING +deletes, +one, -delete, -don't, lost 'delete', lost 'don't', negation differs, numbers differ |
| t5-tiny+guard@kroko+rules | No, no don't delete that file. |  |
| t5-tiny@rules#t2 | No, no, no, no delete that file. | MEANING -don't, lost 'don't', negation differs |
| t5-tiny+guard@rules#t2 | No, no, don't delete that file. |  |
| t5-tiny@rules | No, no, no, no delete that file. | MEANING -don't, lost 'don't', negation differs |
| t5-tiny+guard@rules | No, no, don't delete that file. |  |

### s05 (stutter)

| option | output | flag |
|---|---|---|
| ref | I think that that plan is fine. |  |
| (raw words, untouched) | i think that that plan is fine |  |
| asr-kroko | I think that that plan is fine |  |
| asr-moonshine-base | I think that that plan is fine. |  |
| asr-moonshine-tiny | I think that that plan is fine. |  |
| lfm2.5-1.2b | I think that plan is good. | MEANING +good, -fine, lost 'that that' |
| lfm2.5-1.2b+guard | I think that that plan is fine. |  |
| lfm2.5-1.2b@rules | I think that plan is fine. | MEANING lost 'that that' |
| lfm2.5-1.2b+guard@rules | I think that that plan is fine. |  |
| punct-ct+guard@rules | I think that, that plan is fine. |  |
| punct-ct | i think that，that plan is fine。 | MEANING +that，that, lost 'that that' |
| punct-en+guard>t5-small-gec+guard@rules | I think that that plan is fine. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | I think that that plan is fine. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | I think that that plan is fine. |  |
| punct-en+guard>t5-tiny+guard@rules | I think that that plan is fine. |  |
| punct-en+guard@kroko+rules | I think that that plan is fine. |  |
| punct-en+guard@rules#t2 | I think that that plan is fine. |  |
| punct-en+guard@rules | I think that that plan is fine. |  |
| punct-en | I think that that plan is fine |  |
| qwen2.5-0.5b | I think that plan is fine. | MEANING lost 'that that' |
| qwen2.5-0.5b+guard | I think that that plan is fine. |  |
| qwen2.5-0.5b@kroko+rules | I think that the plan is fine. | MEANING lost 'that that' |
| qwen2.5-0.5b+guard@kroko+rules | I think that that plan is fine. |  |
| qwen2.5-0.5b@rules#t2 | I think that the plan is fine. | MEANING lost 'that that' |
| qwen2.5-0.5b+guard@rules#t2 | I think that that plan is fine. |  |
| qwen2.5-0.5b@rules | I think that the plan is fine. | MEANING lost 'that that' |
| qwen2.5-0.5b+guard@rules | I think that that plan is fine. |  |
| qwen3-0.6b | I think that plan is fine. | MEANING lost 'that that' |
| qwen3-0.6b+guard | I think that that plan is fine. |  |
| qwen3-0.6b@rules | I think that plan is fine. | MEANING lost 'that that' |
| qwen3-0.6b+guard@rules | I think that that plan is fine. |  |
| rules+ | I think that that plan is fine. |  |
| rules+@kroko+rules | I think that that plan is fine. |  |
| rules+@kroko | I think that that plan is fine. |  |
| rules-seam | I think that that plan is fine |  |
| rules-seam@kroko | I think that that plan is fine |  |
| t5-base | I think that that plan is fine. |  |
| t5-base+guard | I think that that plan is fine. |  |
| t5-base@kroko+rules | I think that that plan is fine. |  |
| t5-base+guard@kroko+rules | I think that that plan is fine. |  |
| t5-base@rules | I think that that plan is fine. |  |
| t5-base+guard@rules | I think that that plan is fine. |  |
| t5-mini | I think that that plan is fine. |  |
| t5-mini+guard | I think that that plan is fine. |  |
| t5-mini@rules#t2 | I think that that plan is fine. |  |
| t5-mini+guard@rules#t2 | I think that that plan is fine. |  |
| t5-mini@rules | I think that that plan is fine. |  |
| t5-mini+guard@rules | I think that that plan is fine. |  |
| t5-small-gec | I think that that plan is fine. |  |
| t5-small-gec+guard | I think that that plan is fine. |  |
| t5-small-gec@kroko+rules | I think that that plan is fine. |  |
| t5-small-gec+guard@kroko+rules | I think that that plan is fine. |  |
| t5-small-gec@rules#t2 | I think that that plan is fine. |  |
| t5-small-gec+guard@rules#t2 | I think that that plan is fine. |  |
| t5-small-gec@rules | I think that that plan is fine. |  |
| t5-small-gec+guard@rules | I think that that plan is fine. |  |
| t5-small-synth | I think that that plan is fine. |  |
| t5-small-synth+guard | I think that that plan is fine. |  |
| t5-small-synth@rules | I think that that plan is fine. |  |
| t5-small-synth+guard@rules | I think that that plan is fine. |  |
| t5-tiny+guard>punct-en+guard@rules | I think that that plan is fine. |  |
| t5-tiny | I think that that plan is fine. |  |
| t5-tiny+guard | I think that that plan is fine. |  |
| t5-tiny@kroko+rules | I think that that plan is fine. |  |
| t5-tiny+guard@kroko+rules | I think that that plan is fine. |  |
| t5-tiny@rules#t2 | I think that that plan is fine. |  |
| t5-tiny+guard@rules#t2 | I think that that plan is fine. |  |
| t5-tiny@rules | I think that that plan is fine. |  |
| t5-tiny+guard@rules | I think that that plan is fine. |  |

### r01 (run-on)

| option | output | flag |
|---|---|---|
| ref | Open Firefox and go to the news site, then read me the top three headlines. |  |
| (raw words, untouched) | open firefox and go to the news site then read me the top three headlines |  |
| asr-kroko | Open Firefox and go to the news site, then read me the top three headlines |  |
| asr-moonshine-base | Open Firefox and go to the new site, then read me the top three headlines. | MEANING +new, -news |
| asr-moonshine-tiny | Open Firefox and go to the new site, then read me the top three headlines. | MEANING +new, -news |
| lfm2.5-1.2b | open firefox and go to the news site then read me the top three headlines |  |
| lfm2.5-1.2b+guard | Open firefox and go to the news site then read me the top three headlines. |  |
| lfm2.5-1.2b@rules | Open firefox and go to the news site then read me the top three headlines |  |
| lfm2.5-1.2b+guard@rules | Open firefox and go to the news site then read me the top three headlines. |  |
| punct-ct+guard@rules | Open firefox and go to the news site, then read me the top three headlines. |  |
| punct-ct | open firefox and go to the news site，then read me the top three headlines。 | MEANING +site，then, -site |
| punct-en+guard>t5-small-gec+guard@rules | Open Firefox and go to the news site, then read me the top three headlines. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Open Firefox and go to the news site, then read me the top three headlines. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | Open Firefox and go to the news site, then read me the top three headlines. |  |
| punct-en+guard>t5-tiny+guard@rules | Open Firefox and go to the news site, then read me the top three headlines. |  |
| punct-en+guard@kroko+rules | Open Firefox and go to the news site, then read me the top three headlines. |  |
| punct-en+guard@rules#t2 | Open Firefox and go to the news site, then read me the top three headlines. |  |
| punct-en+guard@rules | Open Firefox and go to the news site, then read me the top three headlines. |  |
| punct-en | Open Firefox and go to the news site, then read me the top three headlines, |  |
| qwen2.5-0.5b | Open Firefox and go to the news site. Then read me the top three headlines. |  |
| qwen2.5-0.5b+guard | Open Firefox and go to the news site. Then read me the top three headlines. |  |
| qwen2.5-0.5b@kroko+rules | Open Firefox and go to the news site, then read me the top three headlines. |  |
| qwen2.5-0.5b+guard@kroko+rules | Open Firefox and go to the news site, then read me the top three headlines. |  |
| qwen2.5-0.5b@rules#t2 | Open Firefox and go to the news site. Then read me the top three headlines. |  |
| qwen2.5-0.5b+guard@rules#t2 | Open Firefox and go to the news site. Then read me the top three headlines. |  |
| qwen2.5-0.5b@rules | Open Firefox and go to the news site. Then read me the top three headlines. |  |
| qwen2.5-0.5b+guard@rules | Open Firefox and go to the news site. Then read me the top three headlines. |  |
| qwen3-0.6b | Open Firefox and go to the news site, then read me the top three headlines. |  |
| qwen3-0.6b+guard | Open Firefox and go to the news site, then read me the top three headlines. |  |
| qwen3-0.6b@rules | Open Firefox and go to the news site, then read me the top three headlines. |  |
| qwen3-0.6b+guard@rules | Open Firefox and go to the news site, then read me the top three headlines. |  |
| rules+ | Open firefox and go to the news site then read me the top three headlines. |  |
| rules+@kroko+rules | Open Firefox and go to the news site, then read me the top three headlines. |  |
| rules+@kroko | Open Firefox and go to the news site, then read me the top three headlines. |  |
| rules-seam | Open firefox and go to the news site then read me the top three headlines |  |
| rules-seam@kroko | Open Firefox and go to the news site, then read me the top three headlines |  |
| t5-base | Open Firefox and go to the news site, then read me the top three headlines. |  |
| t5-base+guard | Open Firefox and go to the news site, then read me the top three headlines. |  |
| t5-base@kroko+rules | Open Firefox and go to the news site, then read me the top three headlines. |  |
| t5-base+guard@kroko+rules | Open Firefox and go to the news site, then read me the top three headlines. |  |
| t5-base@rules | Open Firefox and go to the news site, then read me the top three headlines. |  |
| t5-base+guard@rules | Open Firefox and go to the news site, then read me the top three headlines. |  |
| t5-mini | open Firefox and go to the news site, then read me the top three headlines. |  |
| t5-mini+guard | Open Firefox and go to the news site, then read me the top three headlines. |  |
| t5-mini@rules#t2 | Open Firefox and go to the news site, then read me the top three headlines. |  |
| t5-mini+guard@rules#t2 | Open Firefox and go to the news site, then read me the top three headlines. |  |
| t5-mini@rules | Open Firefox and go to the news site, then read me the top three headlines. |  |
| t5-mini+guard@rules | Open Firefox and go to the news site, then read me the top three headlines. |  |
| t5-small-gec | open firefox and go to the news site, then read to me the top three headlines |  |
| t5-small-gec+guard | Open firefox and go to the news site, then read me the top three headlines. |  |
| t5-small-gec@kroko+rules | Open Firefox and go to the news site, then read to me the top three headlines |  |
| t5-small-gec+guard@kroko+rules | Open Firefox and go to the news site, then read me the top three headlines. |  |
| t5-small-gec@rules#t2 | Open Firefox and go to the news site, then read to me the top three headlines. |  |
| t5-small-gec+guard@rules#t2 | Open Firefox and go to the news site, then read me the top three headlines. |  |
| t5-small-gec@rules | Open Firefox and go to the news site, then read to me the top three headlines. |  |
| t5-small-gec+guard@rules | Open Firefox and go to the news site, then read me the top three headlines. |  |
| t5-small-synth | Open firefox and go to the news site then read the top three headlines. | reworded -me |
| t5-small-synth+guard | Open firefox and go to the news site then read me the top three headlines. |  |
| t5-small-synth@rules | Open firefox and go to the news page then read the top three headlines. | MEANING +page, -site |
| t5-small-synth+guard@rules | Open firefox and go to the news site then read me the top three headlines. |  |
| t5-tiny+guard>punct-en+guard@rules | Open Firefox and go to the news site, then read me the top three headlines. |  |
| t5-tiny | open firefox and go to the news site, then read me the top three headlines. |  |
| t5-tiny+guard | Open firefox and go to the news site, then read me the top three headlines. |  |
| t5-tiny@kroko+rules | Open Firefox and go to the news site, then read me the top three headlines. |  |
| t5-tiny+guard@kroko+rules | Open Firefox and go to the news site, then read me the top three headlines. |  |
| t5-tiny@rules#t2 | Open firefox and go to the news site, then read me the top three headlines. |  |
| t5-tiny+guard@rules#t2 | Open firefox and go to the news site, then read me the top three headlines. |  |
| t5-tiny@rules | Open firefox and go to the news site, then read me the top three headlines. |  |
| t5-tiny+guard@rules | Open firefox and go to the news site, then read me the top three headlines. |  |

### r02 (run-on)

| option | output | flag |
|---|---|---|
| ref | I finished the report. It's in the shared drive. Let me know if you want changes. |  |
| (raw words, untouched) | i finished the report it's in the shared drive let me know if you want changes |  |
| asr-kroko | I finish the report. It's in the shared drive. Let me know if you want changes. | MEANING +finish, -finished |
| asr-moonshine-base | I finish the report, it's in the shared drive, let me know if you want changes. | MEANING +finish, -finished |
| asr-moonshine-tiny | I finish the report. It's in the shared drive. Let me know if you want changes. | MEANING +finish, -finished |
| lfm2.5-1.2b | I finished the report it's in the shared drive let me know if you want changes |  |
| lfm2.5-1.2b+guard | I finished the report it's in the shared drive let me know if you want changes. |  |
| lfm2.5-1.2b@rules | I finished the report it's in the shared drive let me know if you want changes |  |
| lfm2.5-1.2b+guard@rules | I finished the report it's in the shared drive let me know if you want changes. |  |
| punct-ct+guard@rules | I finished the report. it's in the shared drive. let me know if you want changes. |  |
| punct-ct | i finished the report。it's in the shared drive。let me know if you want changes。 | MEANING +drive。let, +report。it's, -drive, -let, -report |
| punct-en+guard>t5-small-gec+guard@rules | I finished the report. It's in the shared drive. Let me know if you want changes. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | I finish the report. It's in the shared drive. Let me. Know if you want changes. | MEANING +finish, -finished |
| punct-en+guard>t5-tiny+guard@rules#t2 | I finished the report. It's in the shared drive. Let me know if you want changes. |  |
| punct-en+guard>t5-tiny+guard@rules | I finished the report. It's in the shared drive. Let me know if you want changes. |  |
| punct-en+guard@kroko+rules | I finish the report. It's in the shared drive. Let me. Know if you want changes. | MEANING +finish, -finished |
| punct-en+guard@rules#t2 | I finished the report. It's in the shared drive. Let me know if you want changes. |  |
| punct-en+guard@rules | I finished the report. It's in the shared drive. Let me know if you want changes. |  |
| punct-en | I finished the report. It's in the shared drive. Let me know if you want changes. |  |
| qwen2.5-0.5b | I finished the report, it's in the shared drive. Let me know if you want changes. |  |
| qwen2.5-0.5b+guard | I finished the report, it's in the shared drive. Let me know if you want changes. |  |
| qwen2.5-0.5b@kroko+rules | I finished the report. It's in the shared drive. Let me know if you want changes. |  |
| qwen2.5-0.5b+guard@kroko+rules | I finish the report. It's in the shared drive. Let me know if you want changes. | MEANING +finish, -finished |
| qwen2.5-0.5b@rules#t2 | I finished the report, it's in the shared drive. Let me know if you want changes. |  |
| qwen2.5-0.5b+guard@rules#t2 | I finished the report, it's in the shared drive. Let me know if you want changes. |  |
| qwen2.5-0.5b@rules | I finished the report, it's in the shared drive. Let me know if you want changes. |  |
| qwen2.5-0.5b+guard@rules | I finished the report, it's in the shared drive. Let me know if you want changes. |  |
| qwen3-0.6b | I finished the report, it's in the shared drive. Let me know if you want changes. |  |
| qwen3-0.6b+guard | I finished the report, it's in the shared drive. Let me know if you want changes. |  |
| qwen3-0.6b@rules | I finished the report, it's in the shared drive. Let me know if you want changes. |  |
| qwen3-0.6b+guard@rules | I finished the report, it's in the shared drive. Let me know if you want changes. |  |
| rules+ | I finished the report it's in the shared drive let me know if you want changes. |  |
| rules+@kroko+rules | I finish the report. It's in the shared drive. Let me know if you want changes. | MEANING +finish, -finished |
| rules+@kroko | I finish the report. It's in the shared drive. Let me know if you want changes. | MEANING +finish, -finished |
| rules-seam | I finished the report it's in the shared drive let me know if you want changes |  |
| rules-seam@kroko | I finish the report. It's in the shared drive. Let me know if you want changes. | MEANING +finish, -finished |
| t5-base | I finished the report, it's in the shared drive. Let me know if you want to make changes. | MEANING +make |
| t5-base+guard | I finished the report, it's in the shared drive. Let me know if you want changes. |  |
| t5-base@kroko+rules | I finished the report. It's in the shared drive. Let me know if you want to make changes. | MEANING +make |
| t5-base+guard@kroko+rules | I finish the report. It's in the shared drive. Let me know if you want changes. | MEANING +finish, -finished |
| t5-base@rules | I finished the report, it's in the shared drive. Let me know if you want to make changes. | MEANING +make |
| t5-base+guard@rules | I finished the report, it's in the shared drive. Let me know if you want changes. |  |
| t5-mini | I finished the report on the shared drive, let me know if you want to change. | MEANING +change, -changes |
| t5-mini+guard | I finished the report it's in the shared drive, let me know if you want changes. |  |
| t5-mini@rules#t2 | I finished the report on the shared drive, let me know if you want to change. | MEANING +change, -changes |
| t5-mini+guard@rules#t2 | I finished the report it's in the shared drive, let me know if you want changes. |  |
| t5-mini@rules | I finished the report on the shared drive, let me know if you want to change. | MEANING +change, -changes |
| t5-mini+guard@rules | I finished the report it's in the shared drive, let me know if you want changes. |  |
| t5-small-gec | I finished the report. It's in the shared drive. Let me know if you want changes. |  |
| t5-small-gec+guard | I finished the report. It's in the shared drive. Let me know if you want changes. |  |
| t5-small-gec@kroko+rules | I finish the report. It's in the shared drive. Let me know if you want changes. | MEANING +finish, -finished |
| t5-small-gec+guard@kroko+rules | I finish the report. It's in the shared drive. Let me know if you want changes. | MEANING +finish, -finished |
| t5-small-gec@rules#t2 | I finished the report. It's in the shared drive. Let me know if you want changes. |  |
| t5-small-gec+guard@rules#t2 | I finished the report. It's in the shared drive. Let me know if you want changes. |  |
| t5-small-gec@rules | I finished the report. It's in the shared drive. Let me know if you want changes. |  |
| t5-small-gec+guard@rules | I finished the report. It's in the shared drive. Let me know if you want changes. |  |
| t5-small-synth | I finished the report in the share drive let me know if you want changes. | MEANING +share, -shared, lost 'shared drive' |
| t5-small-synth+guard | I finished the report it's in the shared drive let me know if you want changes. |  |
| t5-small-synth@rules | I finished the report in the Google Drive let me know if you want changes. | MEANING +google, -shared, lost 'shared drive' |
| t5-small-synth+guard@rules | I finished the report it's in the shared Drive let me know if you want changes. |  |
| t5-tiny+guard>punct-en+guard@rules | I finished the report. It's in the shared drive. Let me know if you want changes. |  |
| t5-tiny | I finished the report. It was on the shared drive, let me know if you want changes. | reworded +it, +was, +on, -it's, -in |
| t5-tiny+guard | I finished the report. it's in the shared drive, let me know if you want changes. |  |
| t5-tiny@kroko+rules | I finish the report. It is in the shared drive. Let me know if you want changes. | MEANING +finish, -finished |
| t5-tiny+guard@kroko+rules | I finish the report. It's in the shared drive. Let me know if you want changes. | MEANING +finish, -finished |
| t5-tiny@rules#t2 | I finished the report. It was on the shared drive, let me know if you want changes. | reworded +it, +was, +on, -it's, -in |
| t5-tiny+guard@rules#t2 | I finished the report. it's in the shared drive, let me know if you want changes. |  |
| t5-tiny@rules | I finished the report. It was on the shared drive, let me know if you want changes. | reworded +it, +was, +on, -it's, -in |
| t5-tiny+guard@rules | I finished the report. it's in the shared drive, let me know if you want changes. |  |

### r03 (run-on)

| option | output | flag |
|---|---|---|
| ref | The build failed again. I don't know why, it worked yesterday. |  |
| (raw words, untouched) | the build failed again i don't know why it worked yesterday |  |
| asr-kroko | The build failed again. I don't know why it worked yesterday |  |
| asr-moonshine-base | The build failed again. I don't know why it worked yesterday. |  |
| asr-moonshine-tiny | The build failed again. I don't know why it worked yesterday. |  |
| lfm2.5-1.2b | The build failed again, I don't know why it worked yesterday. |  |
| lfm2.5-1.2b+guard | The build failed again, I don't know why it worked yesterday. |  |
| lfm2.5-1.2b@rules | The build failed again. I don't know why it worked yesterday. |  |
| lfm2.5-1.2b+guard@rules | The build failed again. I don't know why it worked yesterday. |  |
| punct-ct+guard@rules | The build failed again, I don't know why it worked yesterday. |  |
| punct-ct | the build failed again，i don't know why it worked yesterday。 | MEANING +again，i, -again |
| punct-en+guard>t5-small-gec+guard@rules | The build failed. Again, I don't know why it worked yesterday. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | The build failed, Again. I don't know why it worked yesterday. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | The build failed, again, I don't know why it worked yesterday. |  |
| punct-en+guard>t5-tiny+guard@rules | The build failed, again, I don't know why it worked yesterday. |  |
| punct-en+guard@kroko+rules | The build failed, Again. I, don't know why it worked yesterday. |  |
| punct-en+guard@rules#t2 | The build failed, again, I don't know why it worked yesterday. |  |
| punct-en+guard@rules | The build failed, again, I don't know why it worked yesterday. |  |
| punct-en | The build failed again. I don't know why it worked yesterday. |  |
| qwen2.5-0.5b | The build failed again, I don't know why it worked yesterday. |  |
| qwen2.5-0.5b+guard | The build failed again, I don't know why it worked yesterday. |  |
| qwen2.5-0.5b@kroko+rules | The build failed again. I don't know why it worked yesterday. |  |
| qwen2.5-0.5b+guard@kroko+rules | The build failed again. I don't know why it worked yesterday. |  |
| qwen2.5-0.5b@rules#t2 | The build failed again, I don't know why it worked yesterday. |  |
| qwen2.5-0.5b+guard@rules#t2 | The build failed again, I don't know why it worked yesterday. |  |
| qwen2.5-0.5b@rules | The build failed again, I don't know why it worked yesterday. |  |
| qwen2.5-0.5b+guard@rules | The build failed again, I don't know why it worked yesterday. |  |
| qwen3-0.6b | The build failed again. I don't know why it worked yesterday. |  |
| qwen3-0.6b+guard | The build failed again. I don't know why it worked yesterday. |  |
| qwen3-0.6b@rules | The build failed again. I don't know why it worked yesterday. |  |
| qwen3-0.6b+guard@rules | The build failed again. I don't know why it worked yesterday. |  |
| rules+ | The build failed again I don't know why it worked yesterday. |  |
| rules+@kroko+rules | The build failed again. I don't know why it worked yesterday. |  |
| rules+@kroko | The build failed again. I don't know why it worked yesterday. |  |
| rules-seam | The build failed again I don't know why it worked yesterday |  |
| rules-seam@kroko | The build failed again. I don't know why it worked yesterday |  |
| t5-base | The build failed again, I don't know why it worked yesterday. |  |
| t5-base+guard | The build failed again, I don't know why it worked yesterday. |  |
| t5-base@kroko+rules | The build failed again. I don't know why it worked yesterday. |  |
| t5-base+guard@kroko+rules | The build failed again. I don't know why it worked yesterday. |  |
| t5-base@rules | The build failed again I don't know why it worked yesterday. |  |
| t5-base+guard@rules | The build failed again I don't know why it worked yesterday. |  |
| t5-mini | The build failed again. I don't know why it worked yesterday. |  |
| t5-mini+guard | The build failed again. I don't know why it worked yesterday. |  |
| t5-mini@rules#t2 | The build failed again. I don't know why it worked yesterday. |  |
| t5-mini+guard@rules#t2 | The build failed again. I don't know why it worked yesterday. |  |
| t5-mini@rules | The build failed again. I don't know why it worked yesterday. |  |
| t5-mini+guard@rules | The build failed again. I don't know why it worked yesterday. |  |
| t5-small-gec | the build failed again. I don't know why it worked yesterday. |  |
| t5-small-gec+guard | The build failed again. I don't know why it worked yesterday. |  |
| t5-small-gec@kroko+rules | The build failed again. I don't know why it worked yesterday. |  |
| t5-small-gec+guard@kroko+rules | The build failed again. I don't know why it worked yesterday. |  |
| t5-small-gec@rules#t2 | The build failed again. I don't know why it worked yesterday. |  |
| t5-small-gec+guard@rules#t2 | The build failed again. I don't know why it worked yesterday. |  |
| t5-small-gec@rules | The build failed again. I don't know why it worked yesterday. |  |
| t5-small-gec+guard@rules | The build failed again. I don't know why it worked yesterday. |  |
| t5-small-synth | the builder failed to mention that it worked yesterday. | MEANING +builder, +mention, -again, -build, -don't, -know, -why, lost 'don't', negation differs |
| t5-small-synth+guard | The build failed again i don't know why it worked yesterday. |  |
| t5-small-synth@rules | The builder died a few days ago. | MEANING +ago, +builder, +days, +died, +few, -again, -build, -don't, -failed, -know, -why, -worked, -yesterday, lost 'don't', lost 'yesterday', negation differs |
| t5-small-synth+guard@rules | The build failed again I don't know why it worked yesterday. |  |
| t5-tiny+guard>punct-en+guard@rules | The build failed, Again. I, don't know why it worked yesterday. |  |
| t5-tiny | The build failed again. I don't know why it worked yesterday. |  |
| t5-tiny+guard | The build failed again. I don't know why it worked yesterday. |  |
| t5-tiny@kroko+rules | The build failed again. I don't know why it worked yesterday. |  |
| t5-tiny+guard@kroko+rules | The build failed again. I don't know why it worked yesterday. |  |
| t5-tiny@rules#t2 | The build failed again. I don't know why it worked yesterday. |  |
| t5-tiny+guard@rules#t2 | The build failed again. I don't know why it worked yesterday. |  |
| t5-tiny@rules | The build failed again. I don't know why it worked yesterday. |  |
| t5-tiny+guard@rules | The build failed again. I don't know why it worked yesterday. |  |

### r04 (run-on)

| option | output | flag |
|---|---|---|
| ref | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| (raw words, untouched) | tell siobhan i'll be late the train is delayed by twenty minutes |  |
| asr-kroko | Tell Siobhan I'll be late the train is delayed by twenty minutes. |  |
| asr-moonshine-base | Tell Siobhan I'll be late the train is delayed by 20 minutes. | MEANING +20, -twenty, lost 'twenty', numbers differ |
| asr-moonshine-tiny | Tell Shivan, I'll be late the train is delayed by 20 minutes. | MEANING +20, +shivan, -siobhan, -twenty, lost 'Siobhan', lost 'twenty', numbers differ |
| lfm2.5-1.2b | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| lfm2.5-1.2b+guard | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| lfm2.5-1.2b@rules | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| lfm2.5-1.2b+guard@rules | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| punct-ct+guard@rules | Tell siobhan I'll be late. the train is delayed by twenty minutes. |  |
| punct-ct | tell siobhan i'll be late。the train is delayed by twenty minutes。 | MEANING +late。the, -late |
| punct-en+guard>t5-small-gec+guard@rules | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Tell Siobhan I'll be late. The train is delayed by twenty minutes. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | Tell Siobhan, I'll be late, the train is delayed by twenty minutes. |  |
| punct-en+guard>t5-tiny+guard@rules | Tell Siobhan, I'll be late, the train is delayed by twenty minutes. |  |
| punct-en+guard@kroko+rules | Tell Siobhan I'll be late. The train is delayed by twenty minutes. |  |
| punct-en+guard@rules#t2 | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| punct-en+guard@rules | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| punct-en | Tell Siobhan, I'll be late. The train is delayed by twenty minutes, |  |
| qwen2.5-0.5b | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| qwen2.5-0.5b+guard | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| qwen2.5-0.5b@kroko+rules | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| qwen2.5-0.5b+guard@kroko+rules | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| qwen2.5-0.5b@rules#t2 | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| qwen2.5-0.5b+guard@rules#t2 | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| qwen2.5-0.5b@rules | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| qwen2.5-0.5b+guard@rules | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| qwen3-0.6b | Tell Siobhan I'll be late the train is delayed by twenty minutes. |  |
| qwen3-0.6b+guard | Tell Siobhan I'll be late the train is delayed by twenty minutes. |  |
| qwen3-0.6b@rules | Tell Siobhan I'll be late the train is delayed by twenty minutes. |  |
| qwen3-0.6b+guard@rules | Tell Siobhan I'll be late the train is delayed by twenty minutes. |  |
| rules+ | Tell siobhan I'll be late the train is delayed by twenty minutes. |  |
| rules+@kroko+rules | Tell Siobhan I'll be late the train is delayed by twenty minutes. |  |
| rules+@kroko | Tell Siobhan I'll be late the train is delayed by twenty minutes. |  |
| rules-seam | Tell siobhan I'll be late the train is delayed by twenty minutes |  |
| rules-seam@kroko | Tell Siobhan I'll be late the train is delayed by twenty minutes. |  |
| t5-base | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| t5-base+guard | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| t5-base@kroko+rules | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| t5-base+guard@kroko+rules | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| t5-base@rules | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| t5-base+guard@rules | Tell Siobhan I'll be late, the train is delayed by twenty minutes. |  |
| t5-mini | tell siobhan I'll be late the train is delayed by twenty minutes. |  |
| t5-mini+guard | Tell siobhan I'll be late the train is delayed by twenty minutes. |  |
| t5-mini@rules#t2 | Tell siobhan I am late the train is delayed by twenty minutes. | MEANING -i'll |
| t5-mini+guard@rules#t2 | Tell siobhan I'll be late the train is delayed by twenty minutes. |  |
| t5-mini@rules | Tell siobhan I am late the train is delayed by twenty minutes. | MEANING -i'll |
| t5-mini+guard@rules | Tell siobhan I'll be late the train is delayed by twenty minutes. |  |
| t5-small-gec | tell siobhan i'll be late the train is delayed by twenty minutes |  |
| t5-small-gec+guard | Tell siobhan i'll be late the train is delayed by twenty minutes. |  |
| t5-small-gec@kroko+rules | Tell Siobhan I'll be late. The train is delayed by twenty minutes. |  |
| t5-small-gec+guard@kroko+rules | Tell Siobhan I'll be late. The train is delayed by twenty minutes. |  |
| t5-small-gec@rules#t2 | Tell Siobhan, I'll be late. The train is delayed by twenty minutes. |  |
| t5-small-gec+guard@rules#t2 | Tell Siobhan, I'll be late. The train is delayed by twenty minutes. |  |
| t5-small-gec@rules | Tell Siobhan, I'll be late. The train is delayed by twenty minutes. |  |
| t5-small-gec+guard@rules | Tell Siobhan, I'll be late. The train is delayed by twenty minutes. |  |
| t5-small-synth | say I'll be late the train is delayed by twenty minutes. | MEANING +say, -siobhan, -tell, lost 'Siobhan' |
| t5-small-synth+guard | Tell siobhan I'll be late the train is delayed by twenty minutes. |  |
| t5-small-synth@rules | Tell me about the train station that is delayed by twenty minutes. | MEANING +station, -i'll, -late, -siobhan, lost 'Siobhan' |
| t5-small-synth+guard@rules | Tell siobhan I'll be late the train is delayed by twenty minutes. |  |
| t5-tiny+guard>punct-en+guard@rules | Tell Siobhan I'll be late. the train is delayed by twenty minutes. |  |
| t5-tiny | Tell siobhan I will be late. The train is delayed by twenty minutes. | MEANING -i'll |
| t5-tiny+guard | Tell siobhan i'll be late. The train is delayed by twenty minutes. |  |
| t5-tiny@kroko+rules | Tell Siobhan, I will be late, the train is delayed by twenty minutes. | MEANING -i'll |
| t5-tiny+guard@kroko+rules | Tell Siobhan, I'll be late, the train is delayed by twenty minutes. |  |
| t5-tiny@rules#t2 | Tell me if I'm late, the train is delayed by twenty minutes. | MEANING +i'm, -i'll, -siobhan, lost 'Siobhan' |
| t5-tiny+guard@rules#t2 | Tell siobhan I'll be late, the train is delayed by twenty minutes. |  |
| t5-tiny@rules | Tell me if I'm late, the train is delayed by twenty minutes. | MEANING +i'm, -i'll, -siobhan, lost 'Siobhan' |
| t5-tiny+guard@rules | Tell siobhan I'll be late, the train is delayed by twenty minutes. |  |

### p01 (punctuation)

| option | output | flag |
|---|---|---|
| ref | What time is it in Tokyo? |  |
| (raw words, untouched) | what time is it in tokyo |  |
| asr-kroko | What time is it in Tokyo |  |
| asr-moonshine-base | What time is it in Tokyo? |  |
| asr-moonshine-tiny | What time is it in Tokyo? |  |
| lfm2.5-1.2b | What time is it in Tokyo? |  |
| lfm2.5-1.2b+guard | What time is it in Tokyo? |  |
| lfm2.5-1.2b@rules | What time is it in Tokyo? |  |
| lfm2.5-1.2b+guard@rules | What time is it in Tokyo? |  |
| punct-ct+guard@rules | What time is it in tokyo? |  |
| punct-ct | what time is it in tokyo？ |  |
| punct-en+guard>t5-small-gec+guard@rules | What time is it in Tokyo? |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | What time is it in Tokyo? |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | What time is it in Tokyo? |  |
| punct-en+guard>t5-tiny+guard@rules | What time is it in Tokyo? |  |
| punct-en+guard@kroko+rules | What time is it in Tokyo? |  |
| punct-en+guard@rules#t2 | What time is it in Tokyo? |  |
| punct-en+guard@rules | What time is it in Tokyo? |  |
| punct-en | What time is it in Tokyo, |  |
| qwen2.5-0.5b | What time is it in Tokyo? |  |
| qwen2.5-0.5b+guard | What time is it in Tokyo? |  |
| qwen2.5-0.5b@kroko+rules | What time is it in Tokyo? |  |
| qwen2.5-0.5b+guard@kroko+rules | What time is it in Tokyo? |  |
| qwen2.5-0.5b@rules#t2 | What time is it in Tokyo? |  |
| qwen2.5-0.5b+guard@rules#t2 | What time is it in Tokyo? |  |
| qwen2.5-0.5b@rules | What time is it in Tokyo? |  |
| qwen2.5-0.5b+guard@rules | What time is it in Tokyo? |  |
| qwen3-0.6b | What time is it in Tokyo? |  |
| qwen3-0.6b+guard | What time is it in Tokyo? |  |
| qwen3-0.6b@rules | What time is it in Tokyo? |  |
| qwen3-0.6b+guard@rules | What time is it in Tokyo? |  |
| rules+ | What time is it in tokyo? |  |
| rules+@kroko+rules | What time is it in Tokyo? |  |
| rules+@kroko | What time is it in Tokyo? |  |
| rules-seam | What time is it in tokyo |  |
| rules-seam@kroko | What time is it in Tokyo |  |
| t5-base | What time is it in Tokyo? |  |
| t5-base+guard | What time is it in Tokyo? |  |
| t5-base@kroko+rules | What time is it in Tokyo? |  |
| t5-base+guard@kroko+rules | What time is it in Tokyo? |  |
| t5-base@rules | What time is it in Tokyo? |  |
| t5-base+guard@rules | What time is it in Tokyo? |  |
| t5-mini | What time is it in Tokyo? |  |
| t5-mini+guard | What time is it in Tokyo? |  |
| t5-mini@rules#t2 | What time is it in Tokyo? |  |
| t5-mini+guard@rules#t2 | What time is it in Tokyo? |  |
| t5-mini@rules | What time is it in Tokyo? |  |
| t5-mini+guard@rules | What time is it in Tokyo? |  |
| t5-small-gec | What time is it in Tokyo? |  |
| t5-small-gec+guard | What time is it in Tokyo? |  |
| t5-small-gec@kroko+rules | What time is it in Tokyo? |  |
| t5-small-gec+guard@kroko+rules | What time is it in Tokyo? |  |
| t5-small-gec@rules#t2 | What time is it in Tokyo? |  |
| t5-small-gec+guard@rules#t2 | What time is it in Tokyo? |  |
| t5-small-gec@rules | What time is it in Tokyo? |  |
| t5-small-gec+guard@rules | What time is it in Tokyo? |  |
| t5-small-synth | what time is in Tokyo? | reworded -it |
| t5-small-synth+guard | What time is it in Tokyo? |  |
| t5-small-synth@rules | What time is it in Tokyo? |  |
| t5-small-synth+guard@rules | What time is it in Tokyo? |  |
| t5-tiny+guard>punct-en+guard@rules | What time is it in Tokyo? |  |
| t5-tiny | What time is it in Tokyo? |  |
| t5-tiny+guard | What time is it in Tokyo? |  |
| t5-tiny@kroko+rules | What time is it in Tokyo? |  |
| t5-tiny+guard@kroko+rules | What time is it in Tokyo? |  |
| t5-tiny@rules#t2 | What time is it in Tokyo? |  |
| t5-tiny+guard@rules#t2 | What time is it in Tokyo? |  |
| t5-tiny@rules | What time is it in Tokyo? |  |
| t5-tiny+guard@rules | What time is it in Tokyo? |  |

### p02 (punctuation)

| option | output | flag |
|---|---|---|
| ref | Add eggs, milk, bread and coffee to the shopping list. |  |
| (raw words, untouched) | add eggs milk bread and coffee to the shopping list |  |
| asr-kroko | Add eggs milk, bread, and coffee to the shopping list |  |
| asr-moonshine-base | Add eggs milk bread and coffee to the shopping list. |  |
| asr-moonshine-tiny | Add eggs milk bread and coffee to the shopping list. |  |
| lfm2.5-1.2b | eggs milk bread coffee to shopping list | MEANING -add |
| lfm2.5-1.2b+guard | Add eggs milk bread and coffee to the shopping list. |  |
| lfm2.5-1.2b@rules | eggs milk bread coffee | MEANING -add, -list, -shopping |
| lfm2.5-1.2b+guard@rules | Add eggs milk bread and coffee to the shopping list. |  |
| punct-ct+guard@rules | Add eggs, milk, bread and coffee to the shopping list. |  |
| punct-ct | add eggs，milk，bread and coffee to the shopping list。 | MEANING +eggs，milk，bread, -bread, -eggs, -milk |
| punct-en+guard>t5-small-gec+guard@rules | Add eggs, milk, bread, and coffee to the shopping list. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Add eggs, milk, bread, and coffee to the shopping list. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | Add eggs, milk, bread, and coffee to the shopping list. |  |
| punct-en+guard>t5-tiny+guard@rules | Add eggs, milk, bread, and coffee to the shopping list. |  |
| punct-en+guard@kroko+rules | Add eggs, milk, bread, and coffee to the shopping list. |  |
| punct-en+guard@rules#t2 | Add eggs, milk, bread, and coffee to the shopping list. |  |
| punct-en+guard@rules | Add eggs, milk, bread, and coffee to the shopping list. |  |
| punct-en | Add eggs, milk, bread, and coffee to the shopping list |  |
| qwen2.5-0.5b | Add eggs, milk, bread, and coffee to the shopping list. |  |
| qwen2.5-0.5b+guard | Add eggs, milk, bread, and coffee to the shopping list. |  |
| qwen2.5-0.5b@kroko+rules | Add eggs, milk, bread, and coffee to the shopping list. |  |
| qwen2.5-0.5b+guard@kroko+rules | Add eggs, milk, bread, and coffee to the shopping list. |  |
| qwen2.5-0.5b@rules#t2 | Add eggs, milk, bread, and coffee to the shopping list. |  |
| qwen2.5-0.5b+guard@rules#t2 | Add eggs, milk, bread, and coffee to the shopping list. |  |
| qwen2.5-0.5b@rules | Add eggs, milk, bread, and coffee to the shopping list. |  |
| qwen2.5-0.5b+guard@rules | Add eggs, milk, bread, and coffee to the shopping list. |  |
| qwen3-0.6b | Add eggs, milk, bread, and coffee to the shopping list. |  |
| qwen3-0.6b+guard | Add eggs, milk, bread, and coffee to the shopping list. |  |
| qwen3-0.6b@rules | Add eggs, milk, bread, and coffee to the shopping list. |  |
| qwen3-0.6b+guard@rules | Add eggs, milk, bread, and coffee to the shopping list. |  |
| rules+ | Add eggs milk bread and coffee to the shopping list. |  |
| rules+@kroko+rules | Add eggs milk, bread, and coffee to the shopping list. |  |
| rules+@kroko | Add eggs milk, bread, and coffee to the shopping list. |  |
| rules-seam | Add eggs milk bread and coffee to the shopping list |  |
| rules-seam@kroko | Add eggs milk, bread, and coffee to the shopping list |  |
| t5-base | Add eggs, milk bread and coffee to the shopping list. |  |
| t5-base+guard | Add eggs, milk bread and coffee to the shopping list. |  |
| t5-base@kroko+rules | Add eggs, milk, bread, and coffee to the shopping list. |  |
| t5-base+guard@kroko+rules | Add eggs, milk, bread, and coffee to the shopping list. |  |
| t5-base@rules | Add eggs, milk bread and coffee to the shopping list. |  |
| t5-base+guard@rules | Add eggs, milk bread and coffee to the shopping list. |  |
| t5-mini | add eggs, milk bread and coffee to the shopping list. |  |
| t5-mini+guard | Add eggs, milk bread and coffee to the shopping list. |  |
| t5-mini@rules#t2 | Add eggs, milk bread and coffee to the shopping list. |  |
| t5-mini+guard@rules#t2 | Add eggs, milk bread and coffee to the shopping list. |  |
| t5-mini@rules | Add eggs, milk bread and coffee to the shopping list. |  |
| t5-mini+guard@rules | Add eggs, milk bread and coffee to the shopping list. |  |
| t5-small-gec | add eggs, milk bread and coffee to the shopping list. |  |
| t5-small-gec+guard | Add eggs, milk bread and coffee to the shopping list. |  |
| t5-small-gec@kroko+rules | Add eggs, milk, bread, and coffee to the shopping list. |  |
| t5-small-gec+guard@kroko+rules | Add eggs, milk, bread, and coffee to the shopping list. |  |
| t5-small-gec@rules#t2 | Add eggs, milk bread and coffee to the shopping list. |  |
| t5-small-gec+guard@rules#t2 | Add eggs, milk bread and coffee to the shopping list. |  |
| t5-small-gec@rules | Add eggs, milk bread and coffee to the shopping list. |  |
| t5-small-gec+guard@rules | Add eggs, milk bread and coffee to the shopping list. |  |
| t5-small-synth | add eggs milk and coffee to the shopping list. | MEANING -bread, lost 'bread' |
| t5-small-synth+guard | Add eggs milk bread and coffee to the shopping list. |  |
| t5-small-synth@rules | Add eggs milk and coffee to the shopping list. | MEANING -bread, lost 'bread' |
| t5-small-synth+guard@rules | Add eggs milk bread and coffee to the shopping list. |  |
| t5-tiny+guard>punct-en+guard@rules | Add eggs, milk, bread, and coffee to the shopping list. |  |
| t5-tiny | add eggs, milk, bread and coffee to the shopping list. |  |
| t5-tiny+guard | Add eggs, milk, bread and coffee to the shopping list. |  |
| t5-tiny@kroko+rules | Add eggs, milk, bread, and coffee to the shopping list. |  |
| t5-tiny+guard@kroko+rules | Add eggs, milk, bread, and coffee to the shopping list. |  |
| t5-tiny@rules#t2 | Add eggs, milk, bread and coffee to the shopping list. |  |
| t5-tiny+guard@rules#t2 | Add eggs, milk, bread and coffee to the shopping list. |  |
| t5-tiny@rules | Add eggs, milk, bread and coffee to the shopping list. |  |
| t5-tiny+guard@rules | Add eggs, milk, bread and coffee to the shopping list. |  |

### p03 (punctuation)

| option | output | flag |
|---|---|---|
| ref | Hey Mei, is it going to rain today? |  |
| (raw words, untouched) | hey mei is it going to rain today |  |
| asr-kroko | Hey, May, is it going to rain today? | MEANING +may, -mei, lost 'Mei' |
| asr-moonshine-base | Hey May, is it going to rain today? | MEANING +may, -mei, lost 'Mei' |
| asr-moonshine-tiny | "Hey, May, is it going to rain today?" | MEANING +may, -mei, lost 'Mei' |
| lfm2.5-1.2b | Hey Mei, is it going to rain today? |  |
| lfm2.5-1.2b+guard | Hey Mei, is it going to rain today? |  |
| lfm2.5-1.2b@rules | Hey mei is it going to rain today? |  |
| lfm2.5-1.2b+guard@rules | Hey mei is it going to rain today? |  |
| punct-ct+guard@rules | Hey, mei, is it going to rain today? |  |
| punct-ct | hey，mei，is it going to rain today？ | MEANING +hey，mei，is, -hey, -mei |
| punct-en+guard>t5-small-gec+guard@rules | Hey Mei, is it going to rain today? |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Hey, May, is it going to rain today? | MEANING +may, -mei, lost 'Mei' |
| punct-en+guard>t5-tiny+guard@rules#t2 | Hey Mei, is it going to rain today? |  |
| punct-en+guard>t5-tiny+guard@rules | Hey Mei, is it going to rain today? |  |
| punct-en+guard@kroko+rules | Hey, May, is it going to rain today? | MEANING +may, -mei, lost 'Mei' |
| punct-en+guard@rules#t2 | Hey Mei, is it going to rain today? |  |
| punct-en+guard@rules | Hey Mei, is it going to rain today? |  |
| punct-en | Hey MEI, is it going to rain today, |  |
| qwen2.5-0.5b | Hey, mei, is it going to rain today? |  |
| qwen2.5-0.5b+guard | Hey, mei, is it going to rain today? |  |
| qwen2.5-0.5b@kroko+rules | Hey, May, is it going to rain today? | MEANING +may, -mei, lost 'Mei' |
| qwen2.5-0.5b+guard@kroko+rules | Hey, May, is it going to rain today? | MEANING +may, -mei, lost 'Mei' |
| qwen2.5-0.5b@rules#t2 | Hey mei, is it going to rain today? |  |
| qwen2.5-0.5b+guard@rules#t2 | Hey mei, is it going to rain today? |  |
| qwen2.5-0.5b@rules | Hey mei, is it going to rain today? |  |
| qwen2.5-0.5b+guard@rules | Hey mei, is it going to rain today? |  |
| qwen3-0.6b | Hey Mei, is it going to rain today? |  |
| qwen3-0.6b+guard | Hey Mei, is it going to rain today? |  |
| qwen3-0.6b@rules | Hey Mei, is it going to rain today? |  |
| qwen3-0.6b+guard@rules | Hey Mei, is it going to rain today? |  |
| rules+ | Hey Mei is it going to rain today? |  |
| rules+@kroko+rules | Hey, May, is it going to rain today? | MEANING +may, -mei, lost 'Mei' |
| rules+@kroko | Hey, May, is it going to rain today? | MEANING +may, -mei, lost 'Mei' |
| rules-seam | Hey mei is it going to rain today |  |
| rules-seam@kroko | Hey, May, is it going to rain today? | MEANING +may, -mei, lost 'Mei' |
| t5-base | Hey mei is it going to rain today? |  |
| t5-base+guard | Hey mei is it going to rain today? |  |
| t5-base@kroko+rules | Hey, May, is it going to rain today? | MEANING +may, -mei, lost 'Mei' |
| t5-base+guard@kroko+rules | Hey, May, is it going to rain today? | MEANING +may, -mei, lost 'Mei' |
| t5-base@rules | Hey mei is it going to rain today? |  |
| t5-base+guard@rules | Hey mei is it going to rain today? |  |
| t5-mini | Hey, mei is it going to rain today. |  |
| t5-mini+guard | Hey, mei is it going to rain today. |  |
| t5-mini@rules#t2 | Hey mei is it going to rain today. |  |
| t5-mini+guard@rules#t2 | Hey mei is it going to rain today. |  |
| t5-mini@rules | Hey mei is it going to rain today. |  |
| t5-mini+guard@rules | Hey mei is it going to rain today. |  |
| t5-small-gec | Hey mei, it is going to rain today. | reworded -it |
| t5-small-gec+guard | Hey mei, is it going to rain today. |  |
| t5-small-gec@kroko+rules | Hey, May, is it going to rain today? | MEANING +may, -mei, lost 'Mei' |
| t5-small-gec+guard@kroko+rules | Hey, May, is it going to rain today? | MEANING +may, -mei, lost 'Mei' |
| t5-small-gec@rules#t2 | Hey me, it is going to rain today. | MEANING -mei, lost 'Mei' |
| t5-small-gec+guard@rules#t2 | Hey mei is it going to rain today. |  |
| t5-small-gec@rules | Hey me, it is going to rain today. | MEANING -mei, lost 'Mei' |
| t5-small-gec+guard@rules | Hey mei is it going to rain today. |  |
| t5-small-synth | Hey, I am going to rain today. | MEANING -mei, lost 'Mei' |
| t5-small-synth+guard | Hey, mei is it going to rain today. |  |
| t5-small-synth@rules | Hey guys, it is going to rain soon. | MEANING +guys, +soon, -mei, -today, lost 'Mei' |
| t5-small-synth+guard@rules | Hey mei is it going to rain today? |  |
| t5-tiny+guard>punct-en+guard@rules | Hey, Mei, is it going to rain today. |  |
| t5-tiny | Hey, mei is it going to rain today. |  |
| t5-tiny+guard | Hey, mei is it going to rain today. |  |
| t5-tiny@kroko+rules | Hey, May, is it going to rain today? | MEANING +may, -mei, lost 'Mei' |
| t5-tiny+guard@kroko+rules | Hey, May, is it going to rain today? | MEANING +may, -mei, lost 'Mei' |
| t5-tiny@rules#t2 | Hey, mei is it going to rain today. |  |
| t5-tiny+guard@rules#t2 | Hey, mei is it going to rain today. |  |
| t5-tiny@rules | Hey, mei is it going to rain today. |  |
| t5-tiny+guard@rules | Hey, mei is it going to rain today. |  |

### p04 (punctuation)

| option | output | flag |
|---|---|---|
| ref | Dear Tom, thanks for the update. See you on Monday. |  |
| (raw words, untouched) | dear tom thanks for the update see you on monday |  |
| asr-kroko | Dear Tom, thanks for the updates see you on Monday | MEANING +updates, -update |
| asr-moonshine-base | Dear Tom, thanks for the update. See you on Monday. |  |
| asr-moonshine-tiny | Dear Tom, thanks for the update see you on Monday. |  |
| lfm2.5-1.2b | Hey Tom, thanks for the update. See you Monday. | MEANING +hey, -dear |
| lfm2.5-1.2b+guard | Dear Tom, thanks for the update. See you on Monday. |  |
| lfm2.5-1.2b@rules | Hey tom, thanks for the update. See you monday. | MEANING +hey, -dear |
| lfm2.5-1.2b+guard@rules | Dear tom, thanks for the update. See you on monday. |  |
| punct-ct+guard@rules | Dear tom, thanks for the update, see you on monday. |  |
| punct-ct | dear tom，thanks for the update，see you on monday。 | MEANING +tom，thanks, +update，see, -see, -thanks, -tom, -update |
| punct-en+guard>t5-small-gec+guard@rules | Dear Tom, thanks for the update. See you on Monday. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Dear Tom. Thanks for the updates. See you on Monday. | MEANING +updates, -update |
| punct-en+guard>t5-tiny+guard@rules#t2 | Dear Tom, thanks for the update. See you on Monday. |  |
| punct-en+guard>t5-tiny+guard@rules | Dear Tom, thanks for the update. See you on Monday. |  |
| punct-en+guard@kroko+rules | Dear Tom. thanks for the updates. See you on Monday. | MEANING +updates, -update |
| punct-en+guard@rules#t2 | Dear Tom, thanks for the update. See you on Monday. |  |
| punct-en+guard@rules | Dear Tom, thanks for the update. See you on Monday. |  |
| punct-en | Dear Tom, thanks for the update. See you on Monday, |  |
| qwen2.5-0.5b | Dear Tom, thanks for the update. See you on Monday. |  |
| qwen2.5-0.5b+guard | Dear Tom, thanks for the update. See you on Monday. |  |
| qwen2.5-0.5b@kroko+rules | Dear Tom, thanks for the updates, see you on Monday. | MEANING +updates, -update |
| qwen2.5-0.5b+guard@kroko+rules | Dear Tom, thanks for the updates, see you on Monday. | MEANING +updates, -update |
| qwen2.5-0.5b@rules#t2 | Dear Tom, thanks for the update. See you on Monday. |  |
| qwen2.5-0.5b+guard@rules#t2 | Dear Tom, thanks for the update. See you on Monday. |  |
| qwen2.5-0.5b@rules | Dear Tom, thanks for the update. See you on Monday. |  |
| qwen2.5-0.5b+guard@rules | Dear Tom, thanks for the update. See you on Monday. |  |
| qwen3-0.6b | Dear Tom, thanks for the update. See you on Monday. |  |
| qwen3-0.6b+guard | Dear Tom, thanks for the update. See you on Monday. |  |
| qwen3-0.6b@rules | Dear Tom, thanks for the update. See you on Monday. |  |
| qwen3-0.6b+guard@rules | Dear Tom, thanks for the update. See you on Monday. |  |
| rules+ | Dear tom thanks for the update see you on Monday. |  |
| rules+@kroko+rules | Dear Tom, thanks for the updates see you on Monday. | MEANING +updates, -update |
| rules+@kroko | Dear Tom, thanks for the updates see you on Monday. | MEANING +updates, -update |
| rules-seam | Dear tom thanks for the update see you on monday |  |
| rules-seam@kroko | Dear Tom, thanks for the updates see you on Monday | MEANING +updates, -update |
| t5-base | Dear Tom, thanks for the update, see you on monday. |  |
| t5-base+guard | Dear Tom, thanks for the update, see you on monday. |  |
| t5-base@kroko+rules | Dear Tom, thanks for the updates, see you on Monday. | MEANING +updates, -update |
| t5-base+guard@kroko+rules | Dear Tom, thanks for the updates, see you on Monday. | MEANING +updates, -update |
| t5-base@rules | Dear Tom, thanks for the update, see you on monday. |  |
| t5-base+guard@rules | Dear Tom, thanks for the update, see you on monday. |  |
| t5-mini | Dear Tom, thanks for the update to see you on Monday. | reworded +to |
| t5-mini+guard | Dear Tom, thanks for the update see you on Monday. |  |
| t5-mini@rules#t2 | Dear Tom, thanks for the update to see you on Monday. | reworded +to |
| t5-mini+guard@rules#t2 | Dear Tom, thanks for the update see you on Monday. |  |
| t5-mini@rules | Dear Tom, thanks for the update to see you on Monday. | reworded +to |
| t5-mini+guard@rules | Dear Tom, thanks for the update see you on Monday. |  |
| t5-small-gec | Dear Tom, thanks for the update. See you on Monday |  |
| t5-small-gec+guard | Dear Tom, thanks for the update. See you on Monday. |  |
| t5-small-gec@kroko+rules | Dear Tom, thanks for the updates. See you on Monday | MEANING +updates, -update |
| t5-small-gec+guard@kroko+rules | Dear Tom, thanks for the updates. See you on Monday. | MEANING +updates, -update |
| t5-small-gec@rules#t2 | Dear Tom, thanks for the update. See you on Monday |  |
| t5-small-gec+guard@rules#t2 | Dear Tom, thanks for the update. See you on Monday. |  |
| t5-small-gec@rules | Dear Tom, thanks for the update. See you on Monday |  |
| t5-small-gec+guard@rules | Dear Tom, thanks for the update. See you on Monday. |  |
| t5-small-synth | thanks for the update on Monday. | MEANING -dear, -see, -tom, lost 'Tom' |
| t5-small-synth+guard | Dear tom thanks for the update see you on Monday. |  |
| t5-small-synth@rules | Thank you for the update on Monday. | MEANING +thank, -dear, -see, -thanks, -tom, lost 'Tom' |
| t5-small-synth+guard@rules | Dear tom thanks for the update see you on Monday. |  |
| t5-tiny+guard>punct-en+guard@rules | Dear Tom, thanks for the update. See you on Monday. |  |
| t5-tiny | Dear tom, thanks for the update, see you on Monday |  |
| t5-tiny+guard | Dear tom, thanks for the update, see you on Monday. |  |
| t5-tiny@kroko+rules | Dear Tom, thanks for the updates, see you on Monday. | MEANING +updates, -update |
| t5-tiny+guard@kroko+rules | Dear Tom, thanks for the updates, see you on Monday. | MEANING +updates, -update |
| t5-tiny@rules#t2 | Dear tom, thanks for the update, see you on Monday. |  |
| t5-tiny+guard@rules#t2 | Dear tom, thanks for the update, see you on Monday. |  |
| t5-tiny@rules | Dear tom, thanks for the update, see you on Monday. |  |
| t5-tiny+guard@rules | Dear tom, thanks for the update, see you on Monday. |  |

### p05 (punctuation)

| option | output | flag |
|---|---|---|
| ref | Set a timer for ten minutes. |  |
| (raw words, untouched) | set a timer for ten minutes |  |
| asr-kroko | set a timer for ten minutes |  |
| asr-moonshine-base | Set a timer for 10 minutes. | MEANING +10, -ten, lost 'ten', numbers differ |
| asr-moonshine-tiny | Set a timer for 10 minutes. | MEANING +10, -ten, lost 'ten', numbers differ |
| lfm2.5-1.2b | Set a timer for ten minutes |  |
| lfm2.5-1.2b+guard | Set a timer for ten minutes. |  |
| lfm2.5-1.2b@rules | Set a timer for ten minutes |  |
| lfm2.5-1.2b+guard@rules | Set a timer for ten minutes. |  |
| punct-ct+guard@rules | Set a timer for ten minutes. |  |
| punct-ct | set a timer for ten minutes。 |  |
| punct-en+guard>t5-small-gec+guard@rules | Set a timer for ten minutes. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Set a timer for ten minutes. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | Set a timer for ten minutes. |  |
| punct-en+guard>t5-tiny+guard@rules | Set a timer for ten minutes. |  |
| punct-en+guard@kroko+rules | Set a timer for ten minutes. |  |
| punct-en+guard@rules#t2 | Set a timer for ten minutes. |  |
| punct-en+guard@rules | Set a timer for ten minutes. |  |
| punct-en | Set a timer for ten minutes |  |
| qwen2.5-0.5b | Set a timer for ten minutes. |  |
| qwen2.5-0.5b+guard | Set a timer for ten minutes. |  |
| qwen2.5-0.5b@kroko+rules | Set a timer for ten minutes. |  |
| qwen2.5-0.5b+guard@kroko+rules | Set a timer for ten minutes. |  |
| qwen2.5-0.5b@rules#t2 | Set a timer for ten minutes. |  |
| qwen2.5-0.5b+guard@rules#t2 | Set a timer for ten minutes. |  |
| qwen2.5-0.5b@rules | Set a timer for ten minutes. |  |
| qwen2.5-0.5b+guard@rules | Set a timer for ten minutes. |  |
| qwen3-0.6b | Set a timer for ten minutes. |  |
| qwen3-0.6b+guard | Set a timer for ten minutes. |  |
| qwen3-0.6b@rules | Set a timer for ten minutes. |  |
| qwen3-0.6b+guard@rules | Set a timer for ten minutes. |  |
| rules+ | Set a timer for ten minutes. |  |
| rules+@kroko+rules | Set a timer for ten minutes. |  |
| rules+@kroko | Set a timer for ten minutes. |  |
| rules-seam | Set a timer for ten minutes |  |
| rules-seam@kroko | Set a timer for ten minutes |  |
| t5-base | Set a timer for ten minutes. |  |
| t5-base+guard | Set a timer for ten minutes. |  |
| t5-base@kroko+rules | Set a timer for ten minutes. |  |
| t5-base+guard@kroko+rules | Set a timer for ten minutes. |  |
| t5-base@rules | Set a timer for ten minutes. |  |
| t5-base+guard@rules | Set a timer for ten minutes. |  |
| t5-mini | set a timer for ten minutes. |  |
| t5-mini+guard | Set a timer for ten minutes. |  |
| t5-mini@rules#t2 | Set a timer for ten minutes. |  |
| t5-mini+guard@rules#t2 | Set a timer for ten minutes. |  |
| t5-mini@rules | Set a timer for ten minutes. |  |
| t5-mini+guard@rules | Set a timer for ten minutes. |  |
| t5-small-gec | set a timer for ten minutes |  |
| t5-small-gec+guard | Set a timer for ten minutes. |  |
| t5-small-gec@kroko+rules | Set a timer for ten minutes |  |
| t5-small-gec+guard@kroko+rules | Set a timer for ten minutes. |  |
| t5-small-gec@rules#t2 | Set a timer for ten minutes |  |
| t5-small-gec+guard@rules#t2 | Set a timer for ten minutes. |  |
| t5-small-gec@rules | Set a timer for ten minutes |  |
| t5-small-gec+guard@rules | Set a timer for ten minutes. |  |
| t5-small-synth | set a time for ten minutes. | MEANING +time, -timer |
| t5-small-synth+guard | Set a timer for ten minutes. |  |
| t5-small-synth@rules | set a time for ten minutes. | MEANING +time, -timer |
| t5-small-synth+guard@rules | Set a timer for ten minutes. |  |
| t5-tiny+guard>punct-en+guard@rules | Set a timer for ten minutes. |  |
| t5-tiny | set a timer for ten minutes. |  |
| t5-tiny+guard | Set a timer for ten minutes. |  |
| t5-tiny@kroko+rules | Set a timer for ten minutes. |  |
| t5-tiny+guard@kroko+rules | Set a timer for ten minutes. |  |
| t5-tiny@rules#t2 | Set a timer for ten minutes. |  |
| t5-tiny+guard@rules#t2 | Set a timer for ten minutes. |  |
| t5-tiny@rules | Set a timer for ten minutes. |  |
| t5-tiny+guard@rules | Set a timer for ten minutes. |  |

### h01 (homophone)

| option | output | flag |
|---|---|---|
| ref | They're going to be here at noon. |  |
| (raw words, untouched) | their going to be here at noon |  |
| asr-kroko | They're going to be here at noon. |  |
| asr-moonshine-base | They're going to be here at noon. |  |
| asr-moonshine-tiny | They're going to be here at noon. |  |
| lfm2.5-1.2b | Their going to be here at noon. |  |
| lfm2.5-1.2b+guard | Their going to be here at noon. |  |
| lfm2.5-1.2b@rules | Their going to be here at noon. |  |
| lfm2.5-1.2b+guard@rules | Their going to be here at noon. |  |
| punct-ct+guard@rules | Their going to be here at noon. |  |
| punct-ct | their going to be here at noon。 |  |
| punct-en+guard>t5-small-gec+guard@rules | Their going to be here at noon. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | They're going to be here at noon. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | Their going to be here at noon. |  |
| punct-en+guard>t5-tiny+guard@rules | Their going to be here at noon. |  |
| punct-en+guard@kroko+rules | They're going to be here at noon. |  |
| punct-en+guard@rules#t2 | Their going to be here at noon. |  |
| punct-en+guard@rules | Their going to be here at noon. |  |
| punct-en | Their going to be here at noon |  |
| qwen2.5-0.5b | Their going to be here at noon. |  |
| qwen2.5-0.5b+guard | Their going to be here at noon. |  |
| qwen2.5-0.5b@kroko+rules | They're going to be here at noon. |  |
| qwen2.5-0.5b+guard@kroko+rules | They're going to be here at noon. |  |
| qwen2.5-0.5b@rules#t2 | Their going to be here at noon. |  |
| qwen2.5-0.5b+guard@rules#t2 | Their going to be here at noon. |  |
| qwen2.5-0.5b@rules | Their going to be here at noon. |  |
| qwen2.5-0.5b+guard@rules | Their going to be here at noon. |  |
| qwen3-0.6b | Their going to be here at noon. |  |
| qwen3-0.6b+guard | Their going to be here at noon. |  |
| qwen3-0.6b@rules | Their going to be here at noon. |  |
| qwen3-0.6b+guard@rules | Their going to be here at noon. |  |
| rules+ | Their going to be here at noon. |  |
| rules+@kroko+rules | They're going to be here at noon. |  |
| rules+@kroko | They're going to be here at noon. |  |
| rules-seam | Their going to be here at noon |  |
| rules-seam@kroko | They're going to be here at noon. |  |
| t5-base | They're going to be here at noon. |  |
| t5-base+guard | They're going to be here at noon. |  |
| t5-base@kroko+rules | They're going to be here at noon. |  |
| t5-base+guard@kroko+rules | They're going to be here at noon. |  |
| t5-base@rules | They're going to be here at noon. |  |
| t5-base+guard@rules | They're going to be here at noon. |  |
| t5-mini | their going to be here at noon. |  |
| t5-mini+guard | Their going to be here at noon. |  |
| t5-mini@rules#t2 | They are going to be here at noon. | reworded +they, +are |
| t5-mini+guard@rules#t2 | Their going to be here at noon. |  |
| t5-mini@rules | They are going to be here at noon. | reworded +they, +are |
| t5-mini+guard@rules | Their going to be here at noon. |  |
| t5-small-gec | They are going to be here at noon. | reworded +they, +are |
| t5-small-gec+guard | Their going to be here at noon. |  |
| t5-small-gec@kroko+rules | They're going to be here at noon. |  |
| t5-small-gec+guard@kroko+rules | They're going to be here at noon. |  |
| t5-small-gec@rules#t2 | They are going to be here at noon. | reworded +they, +are |
| t5-small-gec+guard@rules#t2 | Their going to be here at noon. |  |
| t5-small-gec@rules | They are going to be here at noon. | reworded +they, +are |
| t5-small-gec+guard@rules | Their going to be here at noon. |  |
| t5-small-synth | They are going to be there at noon | MEANING -here |
| t5-small-synth+guard | Their going to be here at noon. |  |
| t5-small-synth@rules | They will be there at 5:00 pm. | MEANING +5:00, +pm, -going, -here, -noon, lost 'noon', numbers differ |
| t5-small-synth+guard@rules | Their going to be here at noon. |  |
| t5-tiny+guard>punct-en+guard@rules | Their going to be here at noon. |  |
| t5-tiny | Their going to be here at noon. |  |
| t5-tiny+guard | Their going to be here at noon. |  |
| t5-tiny@kroko+rules | They are going to be here at noon. | reworded +they, +are |
| t5-tiny+guard@kroko+rules | They're going to be here at noon. |  |
| t5-tiny@rules#t2 | They are going to be here at noon. | reworded +they, +are |
| t5-tiny+guard@rules#t2 | Their going to be here at noon. |  |
| t5-tiny@rules | They are going to be here at noon. | reworded +they, +are |
| t5-tiny+guard@rules | Their going to be here at noon. |  |

### h02 (homophone)

| option | output | flag |
|---|---|---|
| ref | You're welcome to join us. |  |
| (raw words, untouched) | your welcome to join us |  |
| asr-kroko | you're welcome to join us. |  |
| asr-moonshine-base | You're welcome to join us. |  |
| asr-moonshine-tiny | You're welcome to join us. |  |
| lfm2.5-1.2b | Hello, welcome to join us | MEANING +hello |
| lfm2.5-1.2b+guard | Your welcome to join us. |  |
| lfm2.5-1.2b@rules | Hey there! | MEANING +hey, -join, -welcome, lost 'join' |
| lfm2.5-1.2b+guard@rules | Your welcome to join us. |  |
| punct-ct+guard@rules | Your welcome to join us. |  |
| punct-ct | your welcome to join us。 |  |
| punct-en+guard>t5-small-gec+guard@rules | Your welcome to join us. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | You're welcome to join Us. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | Your welcome to join us. |  |
| punct-en+guard>t5-tiny+guard@rules | Your welcome to join us. |  |
| punct-en+guard@kroko+rules | You're welcome to join Us. |  |
| punct-en+guard@rules#t2 | Your welcome to join us. |  |
| punct-en+guard@rules | Your welcome to join us. |  |
| punct-en | Your welcome to join us |  |
| qwen2.5-0.5b | Your welcome to join us. |  |
| qwen2.5-0.5b+guard | Your welcome to join us. |  |
| qwen2.5-0.5b@kroko+rules | You're welcome to join us. |  |
| qwen2.5-0.5b+guard@kroko+rules | You're welcome to join us. |  |
| qwen2.5-0.5b@rules#t2 | Your welcome to join us. |  |
| qwen2.5-0.5b+guard@rules#t2 | Your welcome to join us. |  |
| qwen2.5-0.5b@rules | Your welcome to join us. |  |
| qwen2.5-0.5b+guard@rules | Your welcome to join us. |  |
| qwen3-0.6b | Your welcome to join us. |  |
| qwen3-0.6b+guard | Your welcome to join us. |  |
| qwen3-0.6b@rules | Your welcome to join us. |  |
| qwen3-0.6b+guard@rules | Your welcome to join us. |  |
| rules+ | Your welcome to join us. |  |
| rules+@kroko+rules | You're welcome to join us. |  |
| rules+@kroko | You're welcome to join us. |  |
| rules-seam | Your welcome to join us |  |
| rules-seam@kroko | You're welcome to join us. |  |
| t5-base | Your welcome to join us. |  |
| t5-base+guard | Your welcome to join us. |  |
| t5-base@kroko+rules | You're welcome to join us. |  |
| t5-base+guard@kroko+rules | You're welcome to join us. |  |
| t5-base@rules | Your welcome to join us. |  |
| t5-base+guard@rules | Your welcome to join us. |  |
| t5-mini | your welcome to join us. |  |
| t5-mini+guard | Your welcome to join us. |  |
| t5-mini@rules#t2 | Your welcome to join us! |  |
| t5-mini+guard@rules#t2 | Your welcome to join us! |  |
| t5-mini@rules | Your welcome to join us! |  |
| t5-mini+guard@rules | Your welcome to join us! |  |
| t5-small-gec | welcome to join us |  |
| t5-small-gec+guard | Your welcome to join us. |  |
| t5-small-gec@kroko+rules | You're welcome to join us. |  |
| t5-small-gec+guard@kroko+rules | You're welcome to join us. |  |
| t5-small-gec@rules#t2 | Your welcome to join us |  |
| t5-small-gec+guard@rules#t2 | Your welcome to join us. |  |
| t5-small-gec@rules | Your welcome to join us |  |
| t5-small-gec+guard@rules | Your welcome to join us. |  |
| t5-small-synth | Your welcome to join us. |  |
| t5-small-synth+guard | Your welcome to join us. |  |
| t5-small-synth@rules | Your welcome to join us. |  |
| t5-small-synth+guard@rules | Your welcome to join us. |  |
| t5-tiny+guard>punct-en+guard@rules | Your welcome to join Us. |  |
| t5-tiny | Your welcome to join us. |  |
| t5-tiny+guard | Your welcome to join us. |  |
| t5-tiny@kroko+rules | You welcome to join us. | reworded +you |
| t5-tiny+guard@kroko+rules | You're welcome to join us. |  |
| t5-tiny@rules#t2 | Welcome your welcome to join us. |  |
| t5-tiny+guard@rules#t2 | Your welcome to join us. |  |
| t5-tiny@rules | Welcome your welcome to join us. |  |
| t5-tiny+guard@rules | Your welcome to join us. |  |

### h03 (homophone)

| option | output | flag |
|---|---|---|
| ref | The dog wagged its tail. |  |
| (raw words, untouched) | the dog wagged it's tail |  |
| asr-kroko | the dog wagged its tail |  |
| asr-moonshine-base | The dog wagged its tail. |  |
| asr-moonshine-tiny | The dog wagged its tail. |  |
| lfm2.5-1.2b | The dog wagged its tail |  |
| lfm2.5-1.2b+guard | The dog wagged its tail. |  |
| lfm2.5-1.2b@rules | The dog wagged its tail |  |
| lfm2.5-1.2b+guard@rules | The dog wagged its tail. |  |
| punct-ct+guard@rules | The dog wagged it's tail. |  |
| punct-ct | the dog wagged it's tail。 |  |
| punct-en+guard>t5-small-gec+guard@rules | The dog wagged, it's tail. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | The dog wagged its tail. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | The dog wagged, it's tail. |  |
| punct-en+guard>t5-tiny+guard@rules | The dog wagged, it's tail. |  |
| punct-en+guard@kroko+rules | The dog wagged its tail. |  |
| punct-en+guard@rules#t2 | The dog wagged, it's tail. |  |
| punct-en+guard@rules | The dog wagged, it's tail. |  |
| punct-en | The dog wagged, it's tail |  |
| qwen2.5-0.5b | The dog wagged its tail. |  |
| qwen2.5-0.5b+guard | The dog wagged its tail. |  |
| qwen2.5-0.5b@kroko+rules | The dog wagged its tail. |  |
| qwen2.5-0.5b+guard@kroko+rules | The dog wagged its tail. |  |
| qwen2.5-0.5b@rules#t2 | The dog wagged its tail. |  |
| qwen2.5-0.5b+guard@rules#t2 | The dog wagged its tail. |  |
| qwen2.5-0.5b@rules | The dog wagged its tail. |  |
| qwen2.5-0.5b+guard@rules | The dog wagged its tail. |  |
| qwen3-0.6b | The dog wagged its tail. |  |
| qwen3-0.6b+guard | The dog wagged its tail. |  |
| qwen3-0.6b@rules | The dog wagged its tail. |  |
| qwen3-0.6b+guard@rules | The dog wagged its tail. |  |
| rules+ | The dog wagged it's tail. |  |
| rules+@kroko+rules | The dog wagged its tail. |  |
| rules+@kroko | The dog wagged its tail. |  |
| rules-seam | The dog wagged it's tail |  |
| rules-seam@kroko | The dog wagged its tail |  |
| t5-base | The dog wagged it's tail. |  |
| t5-base+guard | The dog wagged it's tail. |  |
| t5-base@kroko+rules | The dog wagged its tail. |  |
| t5-base+guard@kroko+rules | The dog wagged its tail. |  |
| t5-base@rules | The dog wagged it's tail. |  |
| t5-base+guard@rules | The dog wagged it's tail. |  |
| t5-mini | The dog wagged its tail. |  |
| t5-mini+guard | The dog wagged its tail. |  |
| t5-mini@rules#t2 | The dog wagged its tail. |  |
| t5-mini+guard@rules#t2 | The dog wagged its tail. |  |
| t5-mini@rules | The dog wagged its tail. |  |
| t5-mini+guard@rules | The dog wagged its tail. |  |
| t5-small-gec | The dog wagged its tail. |  |
| t5-small-gec+guard | The dog wagged its tail. |  |
| t5-small-gec@kroko+rules | The dog wagged its tail. |  |
| t5-small-gec+guard@kroko+rules | The dog wagged its tail. |  |
| t5-small-gec@rules#t2 | The dog wagged its tail. |  |
| t5-small-gec+guard@rules#t2 | The dog wagged its tail. |  |
| t5-small-gec@rules | The dog wagged its tail. |  |
| t5-small-gec+guard@rules | The dog wagged its tail. |  |
| t5-small-synth | the dog was watching the game. | MEANING +game, +watching, -tail, -wagged, lost 'tail' |
| t5-small-synth+guard | The dog wagged it's tail. |  |
| t5-small-synth@rules | The dog was watching the game. | MEANING +game, +watching, -tail, -wagged, lost 'tail' |
| t5-small-synth+guard@rules | The dog wagged it's tail. |  |
| t5-tiny+guard>punct-en+guard@rules | The dog wagged its tail. |  |
| t5-tiny | The dog wagged its tail. |  |
| t5-tiny+guard | The dog wagged its tail. |  |
| t5-tiny@kroko+rules | The dog wagged its tail. |  |
| t5-tiny+guard@kroko+rules | The dog wagged its tail. |  |
| t5-tiny@rules#t2 | The dog wagged its tail. |  |
| t5-tiny+guard@rules#t2 | The dog wagged its tail. |  |
| t5-tiny@rules | The dog wagged its tail. |  |
| t5-tiny+guard@rules | The dog wagged its tail. |  |

### h04 (homophone)

| option | output | flag |
|---|---|---|
| ref | I don't know whether we should go. |  |
| (raw words, untouched) | i don't know weather we should go |  |
| asr-kroko | I don't know whether we should go. |  |
| asr-moonshine-base | I don't know whether we should go. |  |
| asr-moonshine-tiny | I don't know whether we should go. |  |
| lfm2.5-1.2b | I don't know, we should go. |  |
| lfm2.5-1.2b+guard | I don't know, weather we should go. |  |
| lfm2.5-1.2b@rules | I don't know, we should go. |  |
| lfm2.5-1.2b+guard@rules | I don't know, weather we should go. |  |
| punct-ct+guard@rules | I don't know weather. we should go. |  |
| punct-ct | i don't know weather。we should go。 | MEANING +weather。we |
| punct-en+guard>t5-small-gec+guard@rules | I don't know whether we should go. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | I don't know whether we should go. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | I don't know whether we should go. |  |
| punct-en+guard>t5-tiny+guard@rules | I don't know whether we should go. |  |
| punct-en+guard@kroko+rules | I don't know whether we should go. |  |
| punct-en+guard@rules#t2 | I don't know weather, we should go. |  |
| punct-en+guard@rules | I don't know weather, we should go. |  |
| punct-en | I don't know weather, we should go |  |
| qwen2.5-0.5b | I don't know whether we should go. |  |
| qwen2.5-0.5b+guard | I don't know whether we should go. |  |
| qwen2.5-0.5b@kroko+rules | I don't know whether we should go. |  |
| qwen2.5-0.5b+guard@kroko+rules | I don't know whether we should go. |  |
| qwen2.5-0.5b@rules#t2 | I don't know whether we should go. |  |
| qwen2.5-0.5b+guard@rules#t2 | I don't know whether we should go. |  |
| qwen2.5-0.5b@rules | I don't know whether we should go. |  |
| qwen2.5-0.5b+guard@rules | I don't know whether we should go. |  |
| qwen3-0.6b | I don't know whether we should go. |  |
| qwen3-0.6b+guard | I don't know whether we should go. |  |
| qwen3-0.6b@rules | I don't know whether we should go. |  |
| qwen3-0.6b+guard@rules | I don't know whether we should go. |  |
| rules+ | I don't know weather we should go. |  |
| rules+@kroko+rules | I don't know whether we should go. |  |
| rules+@kroko | I don't know whether we should go. |  |
| rules-seam | I don't know weather we should go |  |
| rules-seam@kroko | I don't know whether we should go. |  |
| t5-base | I don't know whether we should go to the park or not. | MEANING +not, +park, negation differs |
| t5-base+guard | I don't know whether we should go. |  |
| t5-base@kroko+rules | I don't know whether we should go. |  |
| t5-base+guard@kroko+rules | I don't know whether we should go. |  |
| t5-base@rules | I don't know if we should go to the park. | MEANING +park |
| t5-base+guard@rules | I don't know weather we should go. |  |
| t5-mini | I don't know whether we should go. |  |
| t5-mini+guard | I don't know whether we should go. |  |
| t5-mini@rules#t2 | I don't know whether we should go. |  |
| t5-mini+guard@rules#t2 | I don't know whether we should go. |  |
| t5-mini@rules | I don't know whether we should go. |  |
| t5-mini+guard@rules | I don't know whether we should go. |  |
| t5-small-gec | I don't know whether we should go. |  |
| t5-small-gec+guard | I don't know whether we should go. |  |
| t5-small-gec@kroko+rules | I don't know whether we should go. |  |
| t5-small-gec+guard@kroko+rules | I don't know whether we should go. |  |
| t5-small-gec@rules#t2 | I don't know whether we should go |  |
| t5-small-gec+guard@rules#t2 | I don't know whether we should go. |  |
| t5-small-gec@rules | I don't know whether we should go |  |
| t5-small-gec+guard@rules | I don't know whether we should go. |  |
| t5-small-synth | I don't know what we should do. | MEANING +what, -go, lost 'go' |
| t5-small-synth+guard | I don't know weather we should go. |  |
| t5-small-synth@rules | I don't know why we should go. | MEANING +why |
| t5-small-synth+guard@rules | I don't know weather we should go. |  |
| t5-tiny+guard>punct-en+guard@rules | I don't know whether we should go. |  |
| t5-tiny | I don't know whether we should go. |  |
| t5-tiny+guard | I don't know whether we should go. |  |
| t5-tiny@kroko+rules | I don't know whether we should go. |  |
| t5-tiny+guard@kroko+rules | I don't know whether we should go. |  |
| t5-tiny@rules#t2 | I don't know whether we should go. |  |
| t5-tiny+guard@rules#t2 | I don't know whether we should go. |  |
| t5-tiny@rules | I don't know whether we should go. |  |
| t5-tiny+guard@rules | I don't know whether we should go. |  |

### h05 (homophone)

| option | output | flag |
|---|---|---|
| ref | This one is better than the old one. |  |
| (raw words, untouched) | this one is better then the old one |  |
| asr-kroko | This one is better than the old one |  |
| asr-moonshine-base | This one is better than the old one. |  |
| asr-moonshine-tiny | This one is better than the old one. |  |
| lfm2.5-1.2b | this one is better then the old one |  |
| lfm2.5-1.2b+guard | This one is better then the old one. |  |
| lfm2.5-1.2b@rules | This one is better then the old one |  |
| lfm2.5-1.2b+guard@rules | This one is better then the old one. |  |
| punct-ct+guard@rules | This one is better, then the old one. |  |
| punct-ct | this one is better，then the old one。 | MEANING +better，then, -better |
| punct-en+guard>t5-small-gec+guard@rules | This one is better than the old one. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | This one is better than the old one. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | This one is better than the old one. |  |
| punct-en+guard>t5-tiny+guard@rules | This one is better than the old one. |  |
| punct-en+guard@kroko+rules | This one is better than the old one. |  |
| punct-en+guard@rules#t2 | This one is better, then the old one. |  |
| punct-en+guard@rules | This one is better, then the old one. |  |
| punct-en | This one is better, then the old one |  |
| qwen2.5-0.5b | This one is better than the old one. |  |
| qwen2.5-0.5b+guard | This one is better than the old one. |  |
| qwen2.5-0.5b@kroko+rules | This one is better than the old one. |  |
| qwen2.5-0.5b+guard@kroko+rules | This one is better than the old one. |  |
| qwen2.5-0.5b@rules#t2 | This one is better than the old one. |  |
| qwen2.5-0.5b+guard@rules#t2 | This one is better than the old one. |  |
| qwen2.5-0.5b@rules | This one is better than the old one. |  |
| qwen2.5-0.5b+guard@rules | This one is better than the old one. |  |
| qwen3-0.6b | This one is better than the old one. |  |
| qwen3-0.6b+guard | This one is better than the old one. |  |
| qwen3-0.6b@rules | This one is better than the old one. |  |
| qwen3-0.6b+guard@rules | This one is better than the old one. |  |
| rules+ | This one is better then the old one. |  |
| rules+@kroko+rules | This one is better than the old one. |  |
| rules+@kroko | This one is better than the old one. |  |
| rules-seam | This one is better then the old one |  |
| rules-seam@kroko | This one is better than the old one |  |
| t5-base | This one is better than the old one. |  |
| t5-base+guard | This one is better than the old one. |  |
| t5-base@kroko+rules | This one is better than the old one. |  |
| t5-base+guard@kroko+rules | This one is better than the old one. |  |
| t5-base@rules | This one is better than the old one. |  |
| t5-base+guard@rules | This one is better than the old one. |  |
| t5-mini | This one is better than the old one. |  |
| t5-mini+guard | This one is better than the old one. |  |
| t5-mini@rules#t2 | This one is better than the old one. |  |
| t5-mini+guard@rules#t2 | This one is better than the old one. |  |
| t5-mini@rules | This one is better than the old one. |  |
| t5-mini+guard@rules | This one is better than the old one. |  |
| t5-small-gec | This one is better than the old one. |  |
| t5-small-gec+guard | This one is better than the old one. |  |
| t5-small-gec@kroko+rules | This one is better than the old one. |  |
| t5-small-gec+guard@kroko+rules | This one is better than the old one. |  |
| t5-small-gec@rules#t2 | This one is better than the old one. |  |
| t5-small-gec+guard@rules#t2 | This one is better than the old one. |  |
| t5-small-gec@rules | This one is better than the old one. |  |
| t5-small-gec+guard@rules | This one is better than the old one. |  |
| t5-small-synth | this one is better than the old one. |  |
| t5-small-synth+guard | This one is better than the old one. |  |
| t5-small-synth@rules | This one is better than the old one. |  |
| t5-small-synth+guard@rules | This one is better than the old one. |  |
| t5-tiny+guard>punct-en+guard@rules | This one is better than the Old One. |  |
| t5-tiny | This one is better than the old one. |  |
| t5-tiny+guard | This one is better than the old one. |  |
| t5-tiny@kroko+rules | This one is better than the old one. |  |
| t5-tiny+guard@kroko+rules | This one is better than the old one. |  |
| t5-tiny@rules#t2 | This one is better than the old one. |  |
| t5-tiny+guard@rules#t2 | This one is better than the old one. |  |
| t5-tiny@rules | This one is better than the old one. |  |
| t5-tiny+guard@rules | This one is better than the old one. |  |

### h06 (homophone)

| option | output | flag |
|---|---|---|
| ref | I want to go too. |  |
| (raw words, untouched) | i want to go to |  |
| asr-kroko | I want to go to |  |
| asr-moonshine-base | I want to go to |  |
| asr-moonshine-tiny | I want to go to. |  |
| lfm2.5-1.2b | i want to go. |  |
| lfm2.5-1.2b+guard | I want to go. to. |  |
| lfm2.5-1.2b@rules | go to | MEANING -go, -want, lost 'want' |
| lfm2.5-1.2b+guard@rules | I want to go to. |  |
| punct-ct+guard@rules | I want to go to. |  |
| punct-ct | i want to go to。 |  |
| punct-en+guard>t5-small-gec+guard@rules | I want to go to. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | I want to go to. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | I want to go to. |  |
| punct-en+guard>t5-tiny+guard@rules | I want to go to. |  |
| punct-en+guard@kroko+rules | I want to go to. |  |
| punct-en+guard@rules#t2 | I want to go to. |  |
| punct-en+guard@rules | I want to go to. |  |
| punct-en | I want to go to |  |
| qwen2.5-0.5b | I want to go to. |  |
| qwen2.5-0.5b+guard | I want to go to. |  |
| qwen2.5-0.5b@kroko+rules | I want to go to. |  |
| qwen2.5-0.5b+guard@kroko+rules | I want to go to. |  |
| qwen2.5-0.5b@rules#t2 | I want to go to. |  |
| qwen2.5-0.5b+guard@rules#t2 | I want to go to. |  |
| qwen2.5-0.5b@rules | I want to go to. |  |
| qwen2.5-0.5b+guard@rules | I want to go to. |  |
| qwen3-0.6b | I want to go. |  |
| qwen3-0.6b+guard | I want to go. to. |  |
| qwen3-0.6b@rules | I want to go. |  |
| qwen3-0.6b+guard@rules | I want to go. to. |  |
| rules+ | I want to go to. |  |
| rules+@kroko+rules | I want to go to. |  |
| rules+@kroko | I want to go to. |  |
| rules-seam | I want to go to |  |
| rules-seam@kroko | I want to go to |  |
| t5-base | I want to go to a college. | MEANING +college |
| t5-base+guard | I want to go to. |  |
| t5-base@kroko+rules | I want to go to a school. | MEANING +school |
| t5-base+guard@kroko+rules | I want to go to. |  |
| t5-base@rules | I want to go to a school. | MEANING +school |
| t5-base+guard@rules | I want to go to. |  |
| t5-mini | I want to go to bed. | MEANING +bed |
| t5-mini+guard | I want to go to. |  |
| t5-mini@rules#t2 | I want to go to bed. | MEANING +bed |
| t5-mini+guard@rules#t2 | I want to go to. |  |
| t5-mini@rules | I want to go to bed. | MEANING +bed |
| t5-mini+guard@rules | I want to go to. |  |
| t5-small-gec | I want to go to |  |
| t5-small-gec+guard | I want to go to. |  |
| t5-small-gec@kroko+rules | I want to go to |  |
| t5-small-gec+guard@kroko+rules | I want to go to. |  |
| t5-small-gec@rules#t2 | I want to go to |  |
| t5-small-gec+guard@rules#t2 | I want to go to. |  |
| t5-small-gec@rules | I want to go to |  |
| t5-small-gec+guard@rules | I want to go to. |  |
| t5-small-synth | I want to go to the beach. | MEANING +beach |
| t5-small-synth+guard | I want to go to. |  |
| t5-small-synth@rules | I want to go to Hawaii. | MEANING +hawaii |
| t5-small-synth+guard@rules | I want to go to. |  |
| t5-tiny+guard>punct-en+guard@rules | I want to go to. |  |
| t5-tiny | I want to go to school. | MEANING +school |
| t5-tiny+guard | I want to go to. |  |
| t5-tiny@kroko+rules | I want to go to school. | MEANING +school |
| t5-tiny+guard@kroko+rules | I want to go to. |  |
| t5-tiny@rules#t2 | I want to go to school. | MEANING +school |
| t5-tiny+guard@rules#t2 | I want to go to. |  |
| t5-tiny@rules | I want to go to school. | MEANING +school |
| t5-tiny+guard@rules | I want to go to. |  |

### h07 (homophone)

| option | output | flag |
|---|---|---|
| ref | Can you hear me? |  |
| (raw words, untouched) | can you here me |  |
| asr-kroko | Can you hear me? |  |
| asr-moonshine-base | Can you hear me? |  |
| asr-moonshine-tiny | Can you hear me? |  |
| lfm2.5-1.2b | Sure, here it is: | MEANING +sure, lost 'me' |
| lfm2.5-1.2b+guard | Can you here me? |  |
| lfm2.5-1.2b@rules | Sure, here it is: | MEANING +sure, lost 'me' |
| lfm2.5-1.2b+guard@rules | Can you here me? |  |
| punct-ct+guard@rules | Can you here me? |  |
| punct-ct | can you here me？ |  |
| punct-en+guard>t5-small-gec+guard@rules | Can you here me? |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Can you hear me? |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | Can you hear me? |  |
| punct-en+guard>t5-tiny+guard@rules | Can you hear me? |  |
| punct-en+guard@kroko+rules | Can you hear me? |  |
| punct-en+guard@rules#t2 | Can you here me? |  |
| punct-en+guard@rules | Can you here me? |  |
| punct-en | Can you here me |  |
| qwen2.5-0.5b | Can you hear me? |  |
| qwen2.5-0.5b+guard | Can you hear me? |  |
| qwen2.5-0.5b@kroko+rules | Can you hear me? |  |
| qwen2.5-0.5b+guard@kroko+rules | Can you hear me? |  |
| qwen2.5-0.5b@rules#t2 | Can you hear me? |  |
| qwen2.5-0.5b+guard@rules#t2 | Can you hear me? |  |
| qwen2.5-0.5b@rules | Can you hear me? |  |
| qwen2.5-0.5b+guard@rules | Can you hear me? |  |
| qwen3-0.6b | Can you here me? |  |
| qwen3-0.6b+guard | Can you here me? |  |
| qwen3-0.6b@rules | Can you here me? |  |
| qwen3-0.6b+guard@rules | Can you here me? |  |
| rules+ | Can you here me? |  |
| rules+@kroko+rules | Can you hear me? |  |
| rules+@kroko | Can you hear me? |  |
| rules-seam | Can you here me |  |
| rules-seam@kroko | Can you hear me? |  |
| t5-base | Can you here me? |  |
| t5-base+guard | Can you here me? |  |
| t5-base@kroko+rules | Can you hear me? |  |
| t5-base+guard@kroko+rules | Can you hear me? |  |
| t5-base@rules | Can you here me? |  |
| t5-base+guard@rules | Can you here me? |  |
| t5-mini | Can you hear me? |  |
| t5-mini+guard | Can you hear me? |  |
| t5-mini@rules#t2 | Can you hear me? |  |
| t5-mini+guard@rules#t2 | Can you hear me? |  |
| t5-mini@rules | Can you hear me? |  |
| t5-mini+guard@rules | Can you hear me? |  |
| t5-small-gec | Can you come here to me? | MEANING +come |
| t5-small-gec+guard | Can you here me? |  |
| t5-small-gec@kroko+rules | Can you hear me? |  |
| t5-small-gec+guard@kroko+rules | Can you hear me? |  |
| t5-small-gec@rules#t2 | Can you here me? |  |
| t5-small-gec+guard@rules#t2 | Can you here me? |  |
| t5-small-gec@rules | Can you here me? |  |
| t5-small-gec+guard@rules | Can you here me? |  |
| t5-small-synth | can you please tell me? | MEANING +please, +tell |
| t5-small-synth+guard | Can you here me? |  |
| t5-small-synth@rules | Can you please tell me? | MEANING +please, +tell |
| t5-small-synth+guard@rules | Can you here me? |  |
| t5-tiny+guard>punct-en+guard@rules | Can you hear me? |  |
| t5-tiny | Can you hear me? |  |
| t5-tiny+guard | Can you hear me? |  |
| t5-tiny@kroko+rules | Can you hear me? |  |
| t5-tiny+guard@kroko+rules | Can you hear me? |  |
| t5-tiny@rules#t2 | Can you hear me? |  |
| t5-tiny+guard@rules#t2 | Can you hear me? |  |
| t5-tiny@rules | Can you hear me? |  |
| t5-tiny+guard@rules | Can you hear me? |  |

### h08 (homophone)

| option | output | flag |
|---|---|---|
| ref | Please write this down. |  |
| (raw words, untouched) | please right this down |  |
| asr-kroko | Please write this down |  |
| asr-moonshine-base | Please write this down. |  |
| asr-moonshine-tiny | Please write this down. |  |
| lfm2.5-1.2b | Sure, let me clarify: | MEANING +clarify, +let, +sure, -down, -please, lost 'down' |
| lfm2.5-1.2b+guard | Please right this down. |  |
| lfm2.5-1.2b@rules | Sure, let me know. | MEANING +know, +let, +sure, -down, -please, lost 'down' |
| lfm2.5-1.2b+guard@rules | Please right this down. |  |
| punct-ct+guard@rules | Please right this down. |  |
| punct-ct | please right this down。 |  |
| punct-en+guard>t5-small-gec+guard@rules | Please, right, This down. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Please write this down. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | Please, right, This down. |  |
| punct-en+guard>t5-tiny+guard@rules | Please, right, This down. |  |
| punct-en+guard@kroko+rules | Please write this down. |  |
| punct-en+guard@rules#t2 | Please, right, This down. |  |
| punct-en+guard@rules | Please, right, This down. |  |
| punct-en | Please, right, This down, |  |
| qwen2.5-0.5b | Please right this down. |  |
| qwen2.5-0.5b+guard | Please right this down. |  |
| qwen2.5-0.5b@kroko+rules | Please write this down. |  |
| qwen2.5-0.5b+guard@kroko+rules | Please write this down. |  |
| qwen2.5-0.5b@rules#t2 | Please right this down. |  |
| qwen2.5-0.5b+guard@rules#t2 | Please right this down. |  |
| qwen2.5-0.5b@rules | Please right this down. |  |
| qwen2.5-0.5b+guard@rules | Please right this down. |  |
| qwen3-0.6b | Please right this down. |  |
| qwen3-0.6b+guard | Please right this down. |  |
| qwen3-0.6b@rules | Please right this down. |  |
| qwen3-0.6b+guard@rules | Please right this down. |  |
| rules+ | Please right this down. |  |
| rules+@kroko+rules | Please write this down. |  |
| rules+@kroko | Please write this down. |  |
| rules-seam | Please right this down |  |
| rules-seam@kroko | Please write this down |  |
| t5-base | Please correct this down. | MEANING +correct |
| t5-base+guard | Please right this down. |  |
| t5-base@kroko+rules | Please write this down. |  |
| t5-base+guard@kroko+rules | Please write this down. |  |
| t5-base@rules | Please correct this down. | MEANING +correct |
| t5-base+guard@rules | Please right this down. |  |
| t5-mini | Please right this down. |  |
| t5-mini+guard | Please right this down. |  |
| t5-mini@rules#t2 | Please right this down. |  |
| t5-mini+guard@rules#t2 | Please right this down. |  |
| t5-mini@rules | Please right this down. |  |
| t5-mini+guard@rules | Please right this down. |  |
| t5-small-gec | Please right this down |  |
| t5-small-gec+guard | Please right this down. |  |
| t5-small-gec@kroko+rules | Please write this down |  |
| t5-small-gec+guard@kroko+rules | Please write this down. |  |
| t5-small-gec@rules#t2 | Please right this down |  |
| t5-small-gec+guard@rules#t2 | Please right this down. |  |
| t5-small-gec@rules | Please right this down |  |
| t5-small-gec+guard@rules | Please right this down. |  |
| t5-small-synth | please right this down down. |  |
| t5-small-synth+guard | Please right this down. |  |
| t5-small-synth@rules | Please right this down. |  |
| t5-small-synth+guard@rules | Please right this down. |  |
| t5-tiny+guard>punct-en+guard@rules | Please, right? This down. |  |
| t5-tiny | Please right this down. |  |
| t5-tiny+guard | Please right this down. |  |
| t5-tiny@kroko+rules | Please write this down. |  |
| t5-tiny+guard@kroko+rules | Please write this down. |  |
| t5-tiny@rules#t2 | Please right this down. |  |
| t5-tiny+guard@rules#t2 | Please right this down. |  |
| t5-tiny@rules | Please right this down. |  |
| t5-tiny+guard@rules | Please right this down. |  |

### n01 (names)

| option | output | flag |
|---|---|---|
| ref | Email Nguyen and ask if Xochitl got the invoice. |  |
| (raw words, untouched) | email nguyen and ask if xochitl got the invoice |  |
| asr-kroko | email New Yen and ask if Zachado got the invoice | MEANING +new, +yen, +zachado, -nguyen, -xochitl, lost 'Nguyen', lost 'Xochitl' |
| asr-moonshine-base | Email Nguyen and ask if Zachital got the invoice. | MEANING +zachital, -xochitl, lost 'Xochitl' |
| asr-moonshine-tiny | Email Newyen and ask if Zocchital got the invoice. | MEANING +newyen, +zocchital, -nguyen, -xochitl, lost 'Nguyen', lost 'Xochitl' |
| lfm2.5-1.2b | email nguyen and ask if xochitl got the invoice |  |
| lfm2.5-1.2b+guard | Email nguyen and ask if xochitl got the invoice. |  |
| lfm2.5-1.2b@rules | email nguyen and ask if xochitl got the invoice |  |
| lfm2.5-1.2b+guard@rules | Email nguyen and ask if xochitl got the invoice. |  |
| punct-ct+guard@rules | Email nguyen and ask if xochitl got the invoice. |  |
| punct-ct | email nguyen and ask if xochitl got the invoice。 |  |
| punct-en+guard>t5-small-gec+guard@rules | Email Nguyen and ask if Xochitl got the Invoice. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Email New Yen and ask if Zachado got the Invoice. | MEANING +new, +yen, +zachado, -nguyen, -xochitl, lost 'Nguyen', lost 'Xochitl' |
| punct-en+guard>t5-tiny+guard@rules#t2 | Email Nguyen and ask if Xochitl got the Invoice. |  |
| punct-en+guard>t5-tiny+guard@rules | Email Nguyen and ask if Xochitl got the Invoice. |  |
| punct-en+guard@kroko+rules | Email New Yen and ask if Zachado got the Invoice. | MEANING +new, +yen, +zachado, -nguyen, -xochitl, lost 'Nguyen', lost 'Xochitl' |
| punct-en+guard@rules#t2 | Email Nguyen and ask if Xochitl got the Invoice. |  |
| punct-en+guard@rules | Email Nguyen and ask if Xochitl got the Invoice. |  |
| punct-en | Email Nguyen and ask if Xochitl got the Invoice |  |
| qwen2.5-0.5b | Email Nguyen and ask if Xochitl got the invoice. |  |
| qwen2.5-0.5b+guard | Email Nguyen and ask if Xochitl got the invoice. |  |
| qwen2.5-0.5b@kroko+rules | Email New Yen and ask if Zachado got the invoice. | MEANING +new, +yen, +zachado, -nguyen, -xochitl, lost 'Nguyen', lost 'Xochitl' |
| qwen2.5-0.5b+guard@kroko+rules | Email New Yen and ask if Zachado got the invoice. | MEANING +new, +yen, +zachado, -nguyen, -xochitl, lost 'Nguyen', lost 'Xochitl' |
| qwen2.5-0.5b@rules#t2 | Email Nguyen and ask if Xochitl got the invoice. |  |
| qwen2.5-0.5b+guard@rules#t2 | Email Nguyen and ask if Xochitl got the invoice. |  |
| qwen2.5-0.5b@rules | Email Nguyen and ask if Xochitl got the invoice. |  |
| qwen2.5-0.5b+guard@rules | Email Nguyen and ask if Xochitl got the invoice. |  |
| qwen3-0.6b | Email Nguyen and ask if Xochitl got the invoice. |  |
| qwen3-0.6b+guard | Email Nguyen and ask if Xochitl got the invoice. |  |
| qwen3-0.6b@rules | Email Nguyen and ask if Xochitl got the invoice. |  |
| qwen3-0.6b+guard@rules | Email Nguyen and ask if Xochitl got the invoice. |  |
| rules+ | Email nguyen and ask if xochitl got the invoice. |  |
| rules+@kroko+rules | Email New Yen and ask if Zachado got the invoice. | MEANING +new, +yen, +zachado, -nguyen, -xochitl, lost 'Nguyen', lost 'Xochitl' |
| rules+@kroko | Email New Yen and ask if Zachado got the invoice. | MEANING +new, +yen, +zachado, -nguyen, -xochitl, lost 'Nguyen', lost 'Xochitl' |
| rules-seam | Email nguyen and ask if xochitl got the invoice |  |
| rules-seam@kroko | Email New Yen and ask if Zachado got the invoice | MEANING +new, +yen, +zachado, -nguyen, -xochitl, lost 'Nguyen', lost 'Xochitl' |
| t5-base | Email nguyen and ask if xochitl got the invoice. |  |
| t5-base+guard | Email nguyen and ask if xochitl got the invoice. |  |
| t5-base@kroko+rules | Email New Yen and ask if Zachado got the invoice. | MEANING +new, +yen, +zachado, -nguyen, -xochitl, lost 'Nguyen', lost 'Xochitl' |
| t5-base+guard@kroko+rules | Email New Yen and ask if Zachado got the invoice. | MEANING +new, +yen, +zachado, -nguyen, -xochitl, lost 'Nguyen', lost 'Xochitl' |
| t5-base@rules | Email nguyen and ask if xochitl got the invoice. |  |
| t5-base+guard@rules | Email nguyen and ask if xochitl got the invoice. |  |
| t5-mini | email nguyen and ask if xochitl got the invoice. |  |
| t5-mini+guard | Email nguyen and ask if xochitl got the invoice. |  |
| t5-mini@rules#t2 | Email nguyen and ask if a doctor got the invoice. | MEANING +doctor, -xochitl, lost 'Xochitl' |
| t5-mini+guard@rules#t2 | Email nguyen and ask if xochitl got the invoice. |  |
| t5-mini@rules | Email nguyen and ask if a doctor got the invoice. | MEANING +doctor, -xochitl, lost 'Xochitl' |
| t5-mini+guard@rules | Email nguyen and ask if xochitl got the invoice. |  |
| t5-small-gec | email nguyen and ask if xochitl got the invoice |  |
| t5-small-gec+guard | Email nguyen and ask if xochitl got the invoice. |  |
| t5-small-gec@kroko+rules | Email New Yen and ask if Zachado got the invoice | MEANING +new, +yen, +zachado, -nguyen, -xochitl, lost 'Nguyen', lost 'Xochitl' |
| t5-small-gec+guard@kroko+rules | Email New Yen and ask if Zachado got the invoice. | MEANING +new, +yen, +zachado, -nguyen, -xochitl, lost 'Nguyen', lost 'Xochitl' |
| t5-small-gec@rules#t2 | Email nguyen and ask if xochitl got the invoice |  |
| t5-small-gec+guard@rules#t2 | Email nguyen and ask if xochitl got the invoice. |  |
| t5-small-gec@rules | Email nguyen and ask if xochitl got the invoice |  |
| t5-small-gec+guard@rules | Email nguyen and ask if xochitl got the invoice. |  |
| t5-small-synth | email and ask if I got the ticket. | MEANING +ticket, -invoice, -nguyen, -xochitl, lost 'Nguyen', lost 'Xochitl', lost 'invoice' |
| t5-small-synth+guard | Email nguyen and ask if xochitl got the invoice. |  |
| t5-small-synth@rules | Tell me if you got the nagging email. | MEANING +nagging, +tell, -ask, -email, -invoice, -nguyen, -xochitl, lost 'Nguyen', lost 'Xochitl', lost 'invoice' |
| t5-small-synth+guard@rules | Email nguyen and ask if xochitl got the invoice. |  |
| t5-tiny+guard>punct-en+guard@rules | Email Nguyen and ask if Xochitl got the invoice. |  |
| t5-tiny | email nguyen and ask if the account got the invoice. | MEANING +account, -xochitl, lost 'Xochitl' |
| t5-tiny+guard | Email nguyen and ask if xochitl got the invoice. |  |
| t5-tiny@kroko+rules | Email New Yen and ask if Zachado got the invoice. | MEANING +new, +yen, +zachado, -nguyen, -xochitl, lost 'Nguyen', lost 'Xochitl' |
| t5-tiny+guard@kroko+rules | Email New Yen and ask if Zachado got the invoice. | MEANING +new, +yen, +zachado, -nguyen, -xochitl, lost 'Nguyen', lost 'Xochitl' |
| t5-tiny@rules#t2 | Email a nguyen and ask if the account got the invoice. | MEANING +account, -xochitl, lost 'Xochitl' |
| t5-tiny+guard@rules#t2 | Email nguyen and ask if xochitl got the invoice. |  |
| t5-tiny@rules | Email a nguyen and ask if the account got the invoice. | MEANING +account, -xochitl, lost 'Xochitl' |
| t5-tiny+guard@rules | Email nguyen and ask if xochitl got the invoice. |  |

### n02 (names)

| option | output | flag |
|---|---|---|
| ref | Call Andy TMC on his work number. |  |
| (raw words, untouched) | call andy t m c on his work number |  |
| asr-kroko | Call Andy TMC on his work number |  |
| asr-moonshine-base | Call and dtmc on his work number | MEANING +dtmc, -andy, lost 'Andy' |
| asr-moonshine-tiny | Call "anddmc" on his work number. | MEANING +anddmc, -andy, lost 'Andy' |
| lfm2.5-1.2b | call andy t m c on his work number |  |
| lfm2.5-1.2b+guard | Call andy t m c on his work number. |  |
| lfm2.5-1.2b@rules | Call Andy at his work number | reworded +at, -on |
| lfm2.5-1.2b+guard@rules | Call Andy t m c on his work number. |  |
| punct-ct+guard@rules | Call andy t m c on his work number. |  |
| punct-ct | call andy t m c on his work number。 |  |
| punct-en+guard>t5-small-gec+guard@rules | Call Andy T M C on his work number. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Call Andy TMC on his work number. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | Call Andy T M C on his work number. |  |
| punct-en+guard>t5-tiny+guard@rules | Call Andy T M C on his work number. |  |
| punct-en+guard@kroko+rules | Call Andy TMC on his work number. |  |
| punct-en+guard@rules#t2 | Call Andy T M C on his work number. |  |
| punct-en+guard@rules | Call Andy T M C on his work number. |  |
| punct-en | Call Andy T M C on his work number |  |
| qwen2.5-0.5b | Call Andy T. M. C. on his work number. |  |
| qwen2.5-0.5b+guard | Call Andy T. M. C. on his work number. |  |
| qwen2.5-0.5b@kroko+rules | Call Andy TMC on his work number. |  |
| qwen2.5-0.5b+guard@kroko+rules | Call Andy TMC on his work number. |  |
| qwen2.5-0.5b@rules#t2 | Call Andy t. m. c. on his work number. |  |
| qwen2.5-0.5b+guard@rules#t2 | Call Andy t. m. c. on his work number. |  |
| qwen2.5-0.5b@rules | Call Andy t. m. c. on his work number. |  |
| qwen2.5-0.5b+guard@rules | Call Andy t. m. c. on his work number. |  |
| qwen3-0.6b | Call Andy T. M. C. on his work number. |  |
| qwen3-0.6b+guard | Call Andy T. M. C. on his work number. |  |
| qwen3-0.6b@rules | Call Andy T. M. C. on his work number. |  |
| qwen3-0.6b+guard@rules | Call Andy T. M. C. on his work number. |  |
| rules+ | Call andy t m c on his work number. |  |
| rules+@kroko+rules | Call Andy TMC on his work number. |  |
| rules+@kroko | Call Andy TMC on his work number. |  |
| rules-seam | Call andy t m c on his work number |  |
| rules-seam@kroko | Call Andy TMC on his work number |  |
| t5-base | Call andy tomc on his work number. | MEANING +tomc |
| t5-base+guard | Call andy t m c on his work number. |  |
| t5-base@kroko+rules | Call Andy TMC on his work number. |  |
| t5-base+guard@kroko+rules | Call Andy TMC on his work number. |  |
| t5-base@rules | Call andy to make a call on his work number. | MEANING +make |
| t5-base+guard@rules | Call andy t m c on his work number. |  |
| t5-mini | call anybody m c on his work number. | MEANING +anybody, -andy, lost 'Andy' |
| t5-mini+guard | Call andy t m c on his work number. |  |
| t5-mini@rules#t2 | Call anybody to me c on his work number. | MEANING +anybody, -andy, lost 'Andy' |
| t5-mini+guard@rules#t2 | Call andy t m c on his work number. |  |
| t5-mini@rules | Call anybody to me c on his work number. | MEANING +anybody, -andy, lost 'Andy' |
| t5-mini+guard@rules | Call andy t m c on his work number. |  |
| t5-small-gec | call andy t m c on his work number |  |
| t5-small-gec+guard | Call andy t m c on his work number. |  |
| t5-small-gec@kroko+rules | Call Andy TMC on his work number |  |
| t5-small-gec+guard@kroko+rules | Call Andy TMC on his work number. |  |
| t5-small-gec@rules#t2 | Call Andy t m c on his work number |  |
| t5-small-gec+guard@rules#t2 | Call Andy t m c on his work number. |  |
| t5-small-gec@rules | Call Andy t m c on his work number |  |
| t5-small-gec+guard@rules | Call Andy t m c on his work number. |  |
| t5-small-synth | ; I call him on his work number. | MEANING -andy, lost 'Andy' |
| t5-small-synth+guard | Call andy t m c on his work number. |  |
| t5-small-synth@rules | Tell me your work date number. | MEANING +date, +tell, -andy, -call, lost 'Andy', lost 'work number' |
| t5-small-synth+guard@rules | Call andy t m c on his work number. |  |
| t5-tiny+guard>punct-en+guard@rules | Call Andy T M C on his work number. |  |
| t5-tiny | call andy t m c on his work number. |  |
| t5-tiny+guard | Call andy t m c on his work number. |  |
| t5-tiny@kroko+rules | Call Andy TMC on his work number. |  |
| t5-tiny+guard@kroko+rules | Call Andy TMC on his work number. |  |
| t5-tiny@rules#t2 | Call Andy to m c on his work number. | reworded +to |
| t5-tiny+guard@rules#t2 | Call Andy t m c on his work number. |  |
| t5-tiny@rules | Call Andy to m c on his work number. | reworded +to |
| t5-tiny+guard@rules | Call Andy t m c on his work number. |  |

### n03 (names)

| option | output | flag |
|---|---|---|
| ref | Play the new album by boygenius on Spotify. |  |
| (raw words, untouched) | play the new album by boygenius on spotify |  |
| asr-kroko | Play the new album by Boygenius on Spotify |  |
| asr-moonshine-base | Play the new album by Boyginius on Spotify. | MEANING +boyginius, -boygenius, lost 'boygenius' |
| asr-moonshine-tiny | Play the new album by Boyginus on Spotify. | MEANING +boyginus, -boygenius, lost 'boygenius' |
| lfm2.5-1.2b | Play the new album by boygenius on spotify |  |
| lfm2.5-1.2b+guard | Play the new album by boygenius on spotify. |  |
| lfm2.5-1.2b@rules | Play the new album by boygenius on spotify |  |
| lfm2.5-1.2b+guard@rules | Play the new album by boygenius on spotify. |  |
| punct-ct+guard@rules | Play the new album by boygenius on spotify. |  |
| punct-ct | play the new album by boygenius on spotify。 |  |
| punct-en+guard>t5-small-gec+guard@rules | Play the new album by Boygenius on Spotify. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Play the new album by Boygenius on Spotify. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | Play the new album by boygenius on Spotify. |  |
| punct-en+guard>t5-tiny+guard@rules | Play the new album by boygenius on Spotify. |  |
| punct-en+guard@kroko+rules | Play the new album by Boygenius on Spotify. |  |
| punct-en+guard@rules#t2 | Play the new album by boygenius on Spotify. |  |
| punct-en+guard@rules | Play the new album by boygenius on Spotify. |  |
| punct-en | Play the new album by boygenius on Spotify |  |
| qwen2.5-0.5b | Play the new album by Boygenius on Spotify. |  |
| qwen2.5-0.5b+guard | Play the new album by Boygenius on Spotify. |  |
| qwen2.5-0.5b@kroko+rules | Play the new album by Boygenius on Spotify. |  |
| qwen2.5-0.5b+guard@kroko+rules | Play the new album by Boygenius on Spotify. |  |
| qwen2.5-0.5b@rules#t2 | Play the new album by Boygenius on Spotify. |  |
| qwen2.5-0.5b+guard@rules#t2 | Play the new album by Boygenius on Spotify. |  |
| qwen2.5-0.5b@rules | Play the new album by Boygenius on Spotify. |  |
| qwen2.5-0.5b+guard@rules | Play the new album by Boygenius on Spotify. |  |
| qwen3-0.6b | Play the new album by Boygenius on Spotify. |  |
| qwen3-0.6b+guard | Play the new album by Boygenius on Spotify. |  |
| qwen3-0.6b@rules | Play the new album by Boygenius on Spotify. |  |
| qwen3-0.6b+guard@rules | Play the new album by Boygenius on Spotify. |  |
| rules+ | Play the new album by boygenius on spotify. |  |
| rules+@kroko+rules | Play the new album by Boygenius on Spotify. |  |
| rules+@kroko | Play the new album by Boygenius on Spotify. |  |
| rules-seam | Play the new album by boygenius on spotify |  |
| rules-seam@kroko | Play the new album by Boygenius on Spotify |  |
| t5-base | The new album by boygenius is now available on spotify. | MEANING +available, +now, -play |
| t5-base+guard | Play The new album by boygenius on spotify. |  |
| t5-base@kroko+rules | Play the new album by Boygenius on Spotify. |  |
| t5-base+guard@kroko+rules | Play the new album by Boygenius on Spotify. |  |
| t5-base@rules | Play the new album by boygenius on spotify. |  |
| t5-base+guard@rules | Play the new album by boygenius on spotify. |  |
| t5-mini | I play the new album by Boygenius on spotify. | reworded +i |
| t5-mini+guard | Play the new album by Boygenius on spotify. |  |
| t5-mini@rules#t2 | I play the new album by Boygenius on spotify. | reworded +i |
| t5-mini+guard@rules#t2 | Play the new album by Boygenius on spotify. |  |
| t5-mini@rules | I play the new album by Boygenius on spotify. | reworded +i |
| t5-mini+guard@rules | Play the new album by Boygenius on spotify. |  |
| t5-small-gec | play the new album by Boygenius on spotify |  |
| t5-small-gec+guard | Play the new album by Boygenius on spotify. |  |
| t5-small-gec@kroko+rules | Play the new album by Boygenius on Spotify |  |
| t5-small-gec+guard@kroko+rules | Play the new album by Boygenius on Spotify. |  |
| t5-small-gec@rules#t2 | Play the new album by Boygenius on spotify |  |
| t5-small-gec+guard@rules#t2 | Play the new album by Boygenius on spotify. |  |
| t5-small-gec@rules | Play the new album by Boygenius on spotify |  |
| t5-small-gec+guard@rules | Play the new album by Boygenius on spotify. |  |
| t5-small-synth | concert tickets to the concert. | MEANING +concert, +tickets, -album, -boygenius, -new, -play, -spotify, lost 'Spotify', lost 'boygenius' |
| t5-small-synth+guard | Play the new album by boygenius on spotify. |  |
| t5-small-synth@rules | Tell me the new album by name of Paul. | MEANING +name, +paul, +tell, -boygenius, -play, -spotify, lost 'Spotify', lost 'boygenius' |
| t5-small-synth+guard@rules | Play the new album by boygenius on spotify. |  |
| t5-tiny+guard>punct-en+guard@rules | Play the new album by boygenius on Spotify. |  |
| t5-tiny | play the new album by boygenius on Spotify. |  |
| t5-tiny+guard | Play the new album by boygenius on Spotify. |  |
| t5-tiny@kroko+rules | Play the new album by Boygenius on Spotify. |  |
| t5-tiny+guard@kroko+rules | Play the new album by Boygenius on Spotify. |  |
| t5-tiny@rules#t2 | Play the new album by boygenius on Spotify. |  |
| t5-tiny+guard@rules#t2 | Play the new album by boygenius on Spotify. |  |
| t5-tiny@rules | Play the new album by boygenius on Spotify. |  |
| t5-tiny+guard@rules | Play the new album by boygenius on Spotify. |  |

### d01 (numbers)

| option | output | flag |
|---|---|---|
| ref | Transfer 40 dollars to Sam, not 400. |  |
| (raw words, untouched) | transfer 40 dollars to sam not 400 |  |
| asr-kroko | transfer forty dollars to Sam not four hundred | MEANING +forty, +four, +hundred, -40, -400, lost '40', lost '400', numbers differ |
| asr-moonshine-base | Transfer $40 to Sam, not $400. | MEANING -dollars |
| asr-moonshine-tiny | Transfer $40 to Sam not 400. | MEANING -dollars |
| lfm2.5-1.2b | transfer 40 dollars to sam not 400 |  |
| lfm2.5-1.2b+guard | Transfer 40 dollars to sam not 400. |  |
| lfm2.5-1.2b@rules | Transfer 40 dollars to Sam, not 400. |  |
| lfm2.5-1.2b+guard@rules | Transfer 40 dollars to Sam, not 400. |  |
| punct-ct+guard@rules | Transfer 40 dollars to sam not 400. |  |
| punct-ct | transfer 40 dollars to sam not 400。 |  |
| punct-en+guard>t5-small-gec+guard@rules | Transfer 40 dollars to Sam not 400. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Transfer forty dollars to Sam, not four hundred. | MEANING +forty, +four, +hundred, -40, -400, lost '40', lost '400', numbers differ |
| punct-en+guard>t5-tiny+guard@rules#t2 | Transfer 40 dollars to Sam, not 400. |  |
| punct-en+guard>t5-tiny+guard@rules | Transfer 40 dollars to Sam, not 400. |  |
| punct-en+guard@kroko+rules | Transfer forty dollars to Sam not four hundred. | MEANING +forty, +four, +hundred, -40, -400, lost '40', lost '400', numbers differ |
| punct-en+guard@rules#t2 | Transfer 40 dollars to Sam not 400. |  |
| punct-en+guard@rules | Transfer 40 dollars to Sam not 400. |  |
| punct-en | Transfer 40 dollars to Sam not 400 |  |
| qwen2.5-0.5b | Transfer $40 to Sam, not $400. | MEANING -dollars |
| qwen2.5-0.5b+guard | Transfer $40 dollars to Sam, not $400. |  |
| qwen2.5-0.5b@kroko+rules | Transfer forty dollars to Sam, not four hundred. | MEANING +forty, +four, +hundred, -40, -400, lost '40', lost '400', numbers differ |
| qwen2.5-0.5b+guard@kroko+rules | Transfer forty dollars to Sam, not four hundred. | MEANING +forty, +four, +hundred, -40, -400, lost '40', lost '400', numbers differ |
| qwen2.5-0.5b@rules#t2 | Transfer $40 to Sam, not $400. | MEANING -dollars |
| qwen2.5-0.5b+guard@rules#t2 | Transfer $40 dollars to Sam, not $400. |  |
| qwen2.5-0.5b@rules | Transfer $40 to Sam, not $400. | MEANING -dollars |
| qwen2.5-0.5b+guard@rules | Transfer $40 dollars to Sam, not $400. |  |
| qwen3-0.6b | Transfer $40 to Sam. | MEANING -400, -dollars, -not, lost '400', lost 'not', negation differs, numbers differ |
| qwen3-0.6b+guard | Transfer $40 dollars to Sam. not 400. |  |
| qwen3-0.6b@rules | Transfer $40 to Sam. | MEANING -400, -dollars, -not, lost '400', lost 'not', negation differs, numbers differ |
| qwen3-0.6b+guard@rules | Transfer $40 dollars to Sam. not 400. |  |
| rules+ | Transfer 40 dollars to sam not 400. |  |
| rules+@kroko+rules | Transfer forty dollars to Sam not four hundred. | MEANING +forty, +four, +hundred, -40, -400, lost '40', lost '400', numbers differ |
| rules+@kroko | Transfer forty dollars to Sam not four hundred. | MEANING +forty, +four, +hundred, -40, -400, lost '40', lost '400', numbers differ |
| rules-seam | Transfer 40 dollars to sam not 400 |  |
| rules-seam@kroko | Transfer forty dollars to Sam not four hundred | MEANING +forty, +four, +hundred, -40, -400, lost '40', lost '400', numbers differ |
| t5-base | Transfer 40 dollars to Sam, not 400 dollars. |  |
| t5-base+guard | Transfer 40 dollars to Sam, not 400. |  |
| t5-base@kroko+rules | Transfer forty dollars to Sam, not four hundred dollars. | MEANING +forty, +four, +hundred, -40, -400, lost '40', lost '400', numbers differ |
| t5-base+guard@kroko+rules | Transfer forty dollars to Sam, not four hundred. | MEANING +forty, +four, +hundred, -40, -400, lost '40', lost '400', numbers differ |
| t5-base@rules | Transfer 40 dollars to Sam, not 400 dollars. |  |
| t5-base+guard@rules | Transfer 40 dollars to Sam, not 400. |  |
| t5-mini | transfer 40 dollars to the same not 400. | MEANING +same, -sam, lost 'Sam' |
| t5-mini+guard | Transfer 40 dollars to sam not 400. |  |
| t5-mini@rules#t2 | Transfer 40 dollars to the same not 400. | MEANING +same, -sam, lost 'Sam' |
| t5-mini+guard@rules#t2 | Transfer 40 dollars to sam not 400. |  |
| t5-mini@rules | Transfer 40 dollars to the same not 400. | MEANING +same, -sam, lost 'Sam' |
| t5-mini+guard@rules | Transfer 40 dollars to sam not 400. |  |
| t5-small-gec | transfer 40 dollars to sam not 400 |  |
| t5-small-gec+guard | Transfer 40 dollars to sam not 400. |  |
| t5-small-gec@kroko+rules | Transfer forty dollars to Sam not four hundred | MEANING +forty, +four, +hundred, -40, -400, lost '40', lost '400', numbers differ |
| t5-small-gec+guard@kroko+rules | Transfer forty dollars to Sam not four hundred. | MEANING +forty, +four, +hundred, -40, -400, lost '40', lost '400', numbers differ |
| t5-small-gec@rules#t2 | Transfer 40 dollars to Sam not 400 |  |
| t5-small-gec+guard@rules#t2 | Transfer 40 dollars to Sam not 400. |  |
| t5-small-gec@rules | Transfer 40 dollars to Sam not 400 |  |
| t5-small-gec+guard@rules | Transfer 40 dollars to Sam not 400. |  |
| t5-small-synth | deal with 40 dollars in debt. | MEANING +deal, +debt, -400, -not, -sam, -transfer, lost '400', lost 'Sam', lost 'not', negation differs, numbers differ |
| t5-small-synth+guard | Transfer 40 dollars to sam not 400. |  |
| t5-small-synth@rules | Buses to and from the airport. | MEANING +airport, +buses, -40, -400, -dollars, -not, -sam, -transfer, lost '40', lost '400', lost 'Sam', lost 'not', negation differs, numbers differ |
| t5-small-synth+guard@rules | Transfer 40 dollars to sam not 400. |  |
| t5-tiny+guard>punct-en+guard@rules | Transfer 40 dollars to Sam not 400. |  |
| t5-tiny | Transfer 40 dollars to the same as not 400. | MEANING +same, -sam, lost 'Sam' |
| t5-tiny+guard | Transfer 40 dollars to sam not 400. |  |
| t5-tiny@kroko+rules | Transfer forty dollars to Sam not four hundred. | MEANING +forty, +four, +hundred, -40, -400, lost '40', lost '400', numbers differ |
| t5-tiny+guard@kroko+rules | Transfer forty dollars to Sam not four hundred. | MEANING +forty, +four, +hundred, -40, -400, lost '40', lost '400', numbers differ |
| t5-tiny@rules#t2 | Transfer 40 dollars to the same as not 400. | MEANING +same, -sam, lost 'Sam' |
| t5-tiny+guard@rules#t2 | Transfer 40 dollars to sam not 400. |  |
| t5-tiny@rules | Transfer 40 dollars to the same as not 400. | MEANING +same, -sam, lost 'Sam' |
| t5-tiny+guard@rules | Transfer 40 dollars to sam not 400. |  |

### d02 (numbers)

| option | output | flag |
|---|---|---|
| ref | The meeting is at 3:45 on the 15th, not the 16th. |  |
| (raw words, untouched) | the meeting is at 3:45 on the 15th not the 16th |  |
| asr-kroko | The meeting is at three forty five on the fifteenth, not the sixteenth | MEANING +fifteenth, +five, +forty, +sixteenth, +three, -15th, -16th, -3:45, lost '15th', lost '16th', lost '3:45', numbers differ |
| asr-moonshine-base | The meeting is at 3:45 on the 15th, not the 16th. |  |
| asr-moonshine-tiny | The meeting is at 3:45 on the 15th, not the 16th. |  |
| lfm2.5-1.2b | The meeting is at 3:45 on the 15th, not the 16th. |  |
| lfm2.5-1.2b+guard | The meeting is at 3:45 on the 15th, not the 16th. |  |
| lfm2.5-1.2b@rules | The meeting is at 3:45 on the 15th, not the 16th. |  |
| lfm2.5-1.2b+guard@rules | The meeting is at 3:45 on the 15th, not the 16th. |  |
| punct-ct+guard@rules | The meeting is at 3:45 on the 15th, not the 16th. |  |
| punct-ct | the meeting is at 3 : 45 on the 15th，not the 16th。 | MEANING +15th，not, +3, +45, -15th, -3:45, -not, lost '3:45', numbers differ |
| punct-en+guard>t5-small-gec+guard@rules | The meeting is at 3:45 on the 15th, not the 16th. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | The meeting is at three forty five on the Fifteenth, not the sixteenth. | MEANING +fifteenth, +five, +forty, +sixteenth, +three, -15th, -16th, -3:45, lost '15th', lost '16th', lost '3:45', numbers differ |
| punct-en+guard>t5-tiny+guard@rules#t2 | The meeting is at 3:45 on the 15th, not the 16th. |  |
| punct-en+guard>t5-tiny+guard@rules | The meeting is at 3:45 on the 15th, not the 16th. |  |
| punct-en+guard@kroko+rules | The meeting is at three forty five on the Fifteenth, not the sixteenth. | MEANING +fifteenth, +five, +forty, +sixteenth, +three, -15th, -16th, -3:45, lost '15th', lost '16th', lost '3:45', numbers differ |
| punct-en+guard@rules#t2 | The meeting is at 3:45 on the 15th, not the 16th. |  |
| punct-en+guard@rules | The meeting is at 3:45 on the 15th, not the 16th. |  |
| punct-en | The meeting is at 3:45 on the 15TH, not the 16TH | MEANING lost '15th', lost '16th' |
| qwen2.5-0.5b | The meeting is at 3:45 on the 15th, not the 16th. |  |
| qwen2.5-0.5b+guard | The meeting is at 3:45 on the 15th, not the 16th. |  |
| qwen2.5-0.5b@kroko+rules | The meeting is at three forty-five on the fifteenth, not the sixteenth. | MEANING +fifteenth, +forty-five, +sixteenth, +three, -15th, -16th, -3:45, lost '15th', lost '16th', lost '3:45', numbers differ |
| qwen2.5-0.5b+guard@kroko+rules | The meeting is at three forty five on the fifteenth, not the sixteenth. | MEANING +fifteenth, +five, +forty, +sixteenth, +three, -15th, -16th, -3:45, lost '15th', lost '16th', lost '3:45', numbers differ |
| qwen2.5-0.5b@rules#t2 | The meeting is at 3:45 on the 15th, not the 16th. |  |
| qwen2.5-0.5b+guard@rules#t2 | The meeting is at 3:45 on the 15th, not the 16th. |  |
| qwen2.5-0.5b@rules | The meeting is at 3:45 on the 15th, not the 16th. |  |
| qwen2.5-0.5b+guard@rules | The meeting is at 3:45 on the 15th, not the 16th. |  |
| qwen3-0.6b | The meeting is at 3:45 on the 15th, not the 16th. |  |
| qwen3-0.6b+guard | The meeting is at 3:45 on the 15th, not the 16th. |  |
| qwen3-0.6b@rules | The meeting is at 3:45 on the 15th, not the 16th. |  |
| qwen3-0.6b+guard@rules | The meeting is at 3:45 on the 15th, not the 16th. |  |
| rules+ | The meeting is at 3:45 on the 15th not the 16th. |  |
| rules+@kroko+rules | The meeting is at three forty five on the fifteenth, not the sixteenth. | MEANING +fifteenth, +five, +forty, +sixteenth, +three, -15th, -16th, -3:45, lost '15th', lost '16th', lost '3:45', numbers differ |
| rules+@kroko | The meeting is at three forty five on the fifteenth, not the sixteenth. | MEANING +fifteenth, +five, +forty, +sixteenth, +three, -15th, -16th, -3:45, lost '15th', lost '16th', lost '3:45', numbers differ |
| rules-seam | The meeting is at 3:45 on the 15th not the 16th |  |
| rules-seam@kroko | The meeting is at three forty five on the fifteenth, not the sixteenth | MEANING +fifteenth, +five, +forty, +sixteenth, +three, -15th, -16th, -3:45, lost '15th', lost '16th', lost '3:45', numbers differ |
| t5-base | The meeting is at 3:45 on the 15th, not the 16th. |  |
| t5-base+guard | The meeting is at 3:45 on the 15th, not the 16th. |  |
| t5-base@kroko+rules | The meeting is at three forty five on the fifteenth, not the sixteenth. | MEANING +fifteenth, +five, +forty, +sixteenth, +three, -15th, -16th, -3:45, lost '15th', lost '16th', lost '3:45', numbers differ |
| t5-base+guard@kroko+rules | The meeting is at three forty five on the fifteenth, not the sixteenth. | MEANING +fifteenth, +five, +forty, +sixteenth, +three, -15th, -16th, -3:45, lost '15th', lost '16th', lost '3:45', numbers differ |
| t5-base@rules | The meeting is at 3:45 on the 15th, not the 16th. |  |
| t5-base+guard@rules | The meeting is at 3:45 on the 15th, not the 16th. |  |
| t5-mini | The meeting is at 3:45 on the 15th, not the 16th. |  |
| t5-mini+guard | The meeting is at 3:45 on the 15th, not the 16th. |  |
| t5-mini@rules#t2 | The meeting is at 3:45 on the 15th, not the 16th. |  |
| t5-mini+guard@rules#t2 | The meeting is at 3:45 on the 15th, not the 16th. |  |
| t5-mini@rules | The meeting is at 3:45 on the 15th, not the 16th. |  |
| t5-mini+guard@rules | The meeting is at 3:45 on the 15th, not the 16th. |  |
| t5-small-gec | The meeting is at 3:45 on the 15th, not the 16th. |  |
| t5-small-gec+guard | The meeting is at 3:45 on the 15th, not the 16th. |  |
| t5-small-gec@kroko+rules | The meeting is at three forty five on the fifteenth, not the sixteenth | MEANING +fifteenth, +five, +forty, +sixteenth, +three, -15th, -16th, -3:45, lost '15th', lost '16th', lost '3:45', numbers differ |
| t5-small-gec+guard@kroko+rules | The meeting is at three forty five on the fifteenth, not the sixteenth. | MEANING +fifteenth, +five, +forty, +sixteenth, +three, -15th, -16th, -3:45, lost '15th', lost '16th', lost '3:45', numbers differ |
| t5-small-gec@rules#t2 | The meeting is at 3:45 on the 15th, not the 16th. |  |
| t5-small-gec+guard@rules#t2 | The meeting is at 3:45 on the 15th, not the 16th. |  |
| t5-small-gec@rules | The meeting is at 3:45 on the 15th, not the 16th. |  |
| t5-small-gec+guard@rules | The meeting is at 3:45 on the 15th, not the 16th. |  |
| t5-small-synth | the meeting is at 3:45 on the 15th and 16th respectively. | MEANING +respectively, -not, lost 'not', negation differs |
| t5-small-synth+guard | The meeting is at 3:45 on the 15th not the 16th. |  |
| t5-small-synth@rules | The meeting is at 3 p.m. on the 15th and 16th. | MEANING +3, +p.m, -3:45, -not, lost '3:45', lost 'not', negation differs, numbers differ |
| t5-small-synth+guard@rules | The meeting is at 3:45 on the 15th not the 16th. |  |
| t5-tiny+guard>punct-en+guard@rules | The meeting is at 3:45 on the 15th, not the 16th. |  |
| t5-tiny | The meeting is at 3:45 on the 15th of the 16th. | MEANING -not, lost 'not', negation differs |
| t5-tiny+guard | The meeting is at 3:45 on the 15th not the 16th. |  |
| t5-tiny@kroko+rules | The meeting is at three forty five on the fifteenth, not the sixteenth. | MEANING +fifteenth, +five, +forty, +sixteenth, +three, -15th, -16th, -3:45, lost '15th', lost '16th', lost '3:45', numbers differ |
| t5-tiny+guard@kroko+rules | The meeting is at three forty five on the fifteenth, not the sixteenth. | MEANING +fifteenth, +five, +forty, +sixteenth, +three, -15th, -16th, -3:45, lost '15th', lost '16th', lost '3:45', numbers differ |
| t5-tiny@rules#t2 | The meeting is at 3:45 on the 15th of the 16th. | MEANING -not, lost 'not', negation differs |
| t5-tiny+guard@rules#t2 | The meeting is at 3:45 on the 15th not the 16th. |  |
| t5-tiny@rules | The meeting is at 3:45 on the 15th of the 16th. | MEANING -not, lost 'not', negation differs |
| t5-tiny+guard@rules | The meeting is at 3:45 on the 15th not the 16th. |  |

### d03 (numbers)

| option | output | flag |
|---|---|---|
| ref | We need 2.5 liters, which is about 1,200 calories worth. |  |
| (raw words, untouched) | we need 2.5 liters which is about 1,200 calories worth |  |
| asr-kroko | We need two point five liters, which is about one thousand two hundred calories worth | MEANING +five, +hundred, +one, +point, +thousand, +two, -1,200, -2.5, lost '1,200', lost '2.5', numbers differ |
| asr-moonshine-base | We need 2.5 liters, which is about 1,200 calories worth. |  |
| asr-moonshine-tiny | We need 2.5 liters, which is about 1,200 calories worth. |  |
| lfm2.5-1.2b | We need 2.5 liters which is about 1,200 calories worth. |  |
| lfm2.5-1.2b+guard | We need 2.5 liters which is about 1,200 calories worth. |  |
| lfm2.5-1.2b@rules | We need 2.5 liters which is about 1,200 calories worth. |  |
| lfm2.5-1.2b+guard@rules | We need 2.5 liters which is about 1,200 calories worth. |  |
| punct-ct+guard@rules | We need 2.5 liters, which is about 1,200 calories worth. |  |
| punct-ct | we need 2 . 5 liters，which is about 1 , 200 calories worth。 | MEANING +1, +2, +200, +5, +liters，which, -1,200, -2.5, -liters, -which, lost '1,200', lost '2.5', numbers differ |
| punct-en+guard>t5-small-gec+guard@rules | We need 2.5 liters, which is about 1,200 calories worth. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | We need two point five liters, which is about one thousand two hundred calories worth. | MEANING +five, +hundred, +one, +point, +thousand, +two, -1,200, -2.5, lost '1,200', lost '2.5', numbers differ |
| punct-en+guard>t5-tiny+guard@rules#t2 | We need 2.5 liters, which is about 1,200 calories worth. |  |
| punct-en+guard>t5-tiny+guard@rules | We need 2.5 liters, which is about 1,200 calories worth. |  |
| punct-en+guard@kroko+rules | We need two point five liters, which is about one thousand two hundred calories worth. | MEANING +five, +hundred, +one, +point, +thousand, +two, -1,200, -2.5, lost '1,200', lost '2.5', numbers differ |
| punct-en+guard@rules#t2 | We need 2.5 liters, which is about 1,200 calories worth. |  |
| punct-en+guard@rules | We need 2.5 liters, which is about 1,200 calories worth. |  |
| punct-en | We need 2.5 liters, which is about 1,200 calories worth |  |
| qwen2.5-0.5b | We need 2.5 liters, which is about 1,200 calories worth. |  |
| qwen2.5-0.5b+guard | We need 2.5 liters, which is about 1,200 calories worth. |  |
| qwen2.5-0.5b@kroko+rules | We need two point five liters, which is about one thousand two hundred calories worth. | MEANING +five, +hundred, +one, +point, +thousand, +two, -1,200, -2.5, lost '1,200', lost '2.5', numbers differ |
| qwen2.5-0.5b+guard@kroko+rules | We need two point five liters, which is about one thousand two hundred calories worth. | MEANING +five, +hundred, +one, +point, +thousand, +two, -1,200, -2.5, lost '1,200', lost '2.5', numbers differ |
| qwen2.5-0.5b@rules#t2 | We need 2.5 liters, which is about 1,200 calories worth. |  |
| qwen2.5-0.5b+guard@rules#t2 | We need 2.5 liters, which is about 1,200 calories worth. |  |
| qwen2.5-0.5b@rules | We need 2.5 liters, which is about 1,200 calories worth. |  |
| qwen2.5-0.5b+guard@rules | We need 2.5 liters, which is about 1,200 calories worth. |  |
| qwen3-0.6b | We need 2.5 liters, which is about 1,200 calories worth. |  |
| qwen3-0.6b+guard | We need 2.5 liters, which is about 1,200 calories worth. |  |
| qwen3-0.6b@rules | We need 2.5 liters, which is about 1,200 calories worth. |  |
| qwen3-0.6b+guard@rules | We need 2.5 liters, which is about 1,200 calories worth. |  |
| rules+ | We need 2.5 liters which is about 1,200 calories worth. |  |
| rules+@kroko+rules | We need two point five liters, which is about one thousand two hundred calories worth. | MEANING +five, +hundred, +one, +point, +thousand, +two, -1,200, -2.5, lost '1,200', lost '2.5', numbers differ |
| rules+@kroko | We need two point five liters, which is about one thousand two hundred calories worth. | MEANING +five, +hundred, +one, +point, +thousand, +two, -1,200, -2.5, lost '1,200', lost '2.5', numbers differ |
| rules-seam | We need 2.5 liters which is about 1,200 calories worth |  |
| rules-seam@kroko | We need two point five liters, which is about one thousand two hundred calories worth | MEANING +five, +hundred, +one, +point, +thousand, +two, -1,200, -2.5, lost '1,200', lost '2.5', numbers differ |
| t5-base | We need 2.5 liters, which is about 1,200 calories worth. |  |
| t5-base+guard | We need 2.5 liters, which is about 1,200 calories worth. |  |
| t5-base@kroko+rules | We need two point five liters, which is about one thousand two hundred calories worth. | MEANING +five, +hundred, +one, +point, +thousand, +two, -1,200, -2.5, lost '1,200', lost '2.5', numbers differ |
| t5-base+guard@kroko+rules | We need two point five liters, which is about one thousand two hundred calories worth. | MEANING +five, +hundred, +one, +point, +thousand, +two, -1,200, -2.5, lost '1,200', lost '2.5', numbers differ |
| t5-base@rules | We need 2.5 liters, which is about 1,200 calories worth. |  |
| t5-base+guard@rules | We need 2.5 liters, which is about 1,200 calories worth. |  |
| t5-mini | We need 2.5 liters which are about 1,200 calories worth. | reworded +are, -is |
| t5-mini+guard | We need 2.5 liters which is about 1,200 calories worth. |  |
| t5-mini@rules#t2 | We need 2.5 liters which are about 1,200 calories worth. | reworded +are, -is |
| t5-mini+guard@rules#t2 | We need 2.5 liters which is about 1,200 calories worth. |  |
| t5-mini@rules | We need 2.5 liters which are about 1,200 calories worth. | reworded +are, -is |
| t5-mini+guard@rules | We need 2.5 liters which is about 1,200 calories worth. |  |
| t5-small-gec | We need 2.5 liters, which is about 1,200 calories worth |  |
| t5-small-gec+guard | We need 2.5 liters, which is about 1,200 calories worth. |  |
| t5-small-gec@kroko+rules | We need two point five liters, which is about one thousand two hundred calories worth | MEANING +five, +hundred, +one, +point, +thousand, +two, -1,200, -2.5, lost '1,200', lost '2.5', numbers differ |
| t5-small-gec+guard@kroko+rules | We need two point five liters, which is about one thousand two hundred calories worth. | MEANING +five, +hundred, +one, +point, +thousand, +two, -1,200, -2.5, lost '1,200', lost '2.5', numbers differ |
| t5-small-gec@rules#t2 | We need 2.5 liters, which is about 1,200 calories worth |  |
| t5-small-gec+guard@rules#t2 | We need 2.5 liters, which is about 1,200 calories worth. |  |
| t5-small-gec@rules | We need 2.5 liters, which is about 1,200 calories worth |  |
| t5-small-gec+guard@rules | We need 2.5 liters, which is about 1,200 calories worth. |  |
| t5-small-synth | We need a 1.5 liter liter lion which is about 430 liters worth of lion. | MEANING +1.5, +430, +lion, +liter, -1,200, -2.5, -calories, -liters, lost '1,200', lost '2.5', numbers differ |
| t5-small-synth+guard | We need 2.5 liters which is about 1,200 calories worth. |  |
| t5-small-synth@rules | We need 1.5 liters which is about 320 liters. | MEANING +1.5, +320, -1,200, -2.5, -calories, -worth, lost '1,200', lost '2.5', numbers differ |
| t5-small-synth+guard@rules | We need 2.5 liters which is about 1,200 calories worth. |  |
| t5-tiny+guard>punct-en+guard@rules | We need 2.5 liters, which is about 1,200 calories, worth. |  |
| t5-tiny | We need 2.5 liters, which is about 1,200 calories worth. |  |
| t5-tiny+guard | We need 2.5 liters, which is about 1,200 calories worth. |  |
| t5-tiny@kroko+rules | We need two points of five liters, which is about one thousand two hundred calories worth. | MEANING +five, +hundred, +one, +points, +thousand, +two, -1,200, -2.5, lost '1,200', lost '2.5', numbers differ |
| t5-tiny+guard@kroko+rules | We need two point five liters, which is about one thousand two hundred calories worth. | MEANING +five, +hundred, +one, +point, +thousand, +two, -1,200, -2.5, lost '1,200', lost '2.5', numbers differ |
| t5-tiny@rules#t2 | We need 2.5 liters, which is about 1,200 calories worth. |  |
| t5-tiny+guard@rules#t2 | We need 2.5 liters, which is about 1,200 calories worth. |  |
| t5-tiny@rules | We need 2.5 liters, which is about 1,200 calories worth. |  |
| t5-tiny+guard@rules | We need 2.5 liters, which is about 1,200 calories worth. |  |

### d04 (numbers)

| option | output | flag |
|---|---|---|
| ref | Meet me at four, no wait, five o'clock. |  |
| (raw words, untouched) | meet me at four no wait five o'clock |  |
| asr-kroko | Meet me at four no wait five o'clock |  |
| asr-moonshine-base | Meet me at four, no weight five o'clock. | MEANING +weight, -wait, lost 'wait' |
| asr-moonshine-tiny | Meet me at four, no weight, five o'clock. | MEANING +weight, -wait, lost 'wait' |
| lfm2.5-1.2b | Meet me at four no wait five o'clock |  |
| lfm2.5-1.2b+guard | Meet me at four no wait five o'clock. |  |
| lfm2.5-1.2b@rules | Meet me at four no wait five o'clock |  |
| lfm2.5-1.2b+guard@rules | Meet me at four no wait five o'clock. |  |
| punct-ct+guard@rules | Meet me at four. no wait five o'clock. |  |
| punct-ct | meet me at four。no wait five o'clock。 | MEANING +four。no, -four, -no |
| punct-en+guard>t5-small-gec+guard@rules | Meet me at four. No wait, five, o'clock. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Meet me at four. No wait, five, o'clock. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | Meet me at four. No wait, five, o'clock. |  |
| punct-en+guard>t5-tiny+guard@rules | Meet me at four. No wait, five, o'clock. |  |
| punct-en+guard@kroko+rules | Meet me at four. No wait, five, o'clock. |  |
| punct-en+guard@rules#t2 | Meet me at four. No wait, five, o'clock. |  |
| punct-en+guard@rules | Meet me at four. No wait, five, o'clock. |  |
| punct-en | Meet me at four. No wait, five, o'clock |  |
| qwen2.5-0.5b | Meet me at four, no wait, five o'clock. |  |
| qwen2.5-0.5b+guard | Meet me at four, no wait, five o'clock. |  |
| qwen2.5-0.5b@kroko+rules | Meet me at four, no wait five o'clock. |  |
| qwen2.5-0.5b+guard@kroko+rules | Meet me at four, no wait five o'clock. |  |
| qwen2.5-0.5b@rules#t2 | Meet me at four, no wait five o'clock. |  |
| qwen2.5-0.5b+guard@rules#t2 | Meet me at four, no wait five o'clock. |  |
| qwen2.5-0.5b@rules | Meet me at four, no wait five o'clock. |  |
| qwen2.5-0.5b+guard@rules | Meet me at four, no wait five o'clock. |  |
| qwen3-0.6b | Meet me at four no wait five o'clock. |  |
| qwen3-0.6b+guard | Meet me at four no wait five o'clock. |  |
| qwen3-0.6b@rules | Meet me at four no wait five o'clock. |  |
| qwen3-0.6b+guard@rules | Meet me at four no wait five o'clock. |  |
| rules+ | Meet me at four no wait five o'clock. |  |
| rules+@kroko+rules | Meet me at four no wait five o'clock. |  |
| rules+@kroko | Meet me at four no wait five o'clock. |  |
| rules-seam | Meet me at four no wait five o'clock |  |
| rules-seam@kroko | Meet me at four no wait five o'clock |  |
| t5-base | Meet me at four, no wait five o'clock. |  |
| t5-base+guard | Meet me at four, no wait five o'clock. |  |
| t5-base@kroko+rules | Meet me at four, no wait five o'clock. |  |
| t5-base+guard@kroko+rules | Meet me at four, no wait five o'clock. |  |
| t5-base@rules | Meet me at four, no wait five o'clock. |  |
| t5-base+guard@rules | Meet me at four, no wait five o'clock. |  |
| t5-mini | meet me at four no wait five o'clock. |  |
| t5-mini+guard | Meet me at four no wait five o'clock. |  |
| t5-mini@rules#t2 | Meet me at four no wait five o'clock. |  |
| t5-mini+guard@rules#t2 | Meet me at four no wait five o'clock. |  |
| t5-mini@rules | Meet me at four no wait five o'clock. |  |
| t5-mini+guard@rules | Meet me at four no wait five o'clock. |  |
| t5-small-gec | meet me at four no wait five o' clock | MEANING +clock, +o', -o'clock |
| t5-small-gec+guard | Meet me at four no wait five o'clock. |  |
| t5-small-gec@kroko+rules | Meet me at four no wait five o' clock | MEANING +clock, +o', -o'clock |
| t5-small-gec+guard@kroko+rules | Meet me at four no wait five o'clock. |  |
| t5-small-gec@rules#t2 | Meet me at four no wait five o' clock | MEANING +clock, +o', -o'clock |
| t5-small-gec+guard@rules#t2 | Meet me at four no wait five o'clock. |  |
| t5-small-gec@rules | Meet me at four no wait five o' clock | MEANING +clock, +o', -o'clock |
| t5-small-gec+guard@rules | Meet me at four no wait five o'clock. |  |
| t5-small-synth | ; I met a couple of lawyers at a small town. | MEANING +couple, +lawyers, +met, +small, +town, -five, -four, -meet, -no, -o'clock, -wait, lost 'five', lost 'four', lost 'wait', negation differs, numbers differ |
| t5-small-synth+guard | Meet me at four no wait five o'clock. |  |
| t5-small-synth@rules | Meet me at a four-week camp. | MEANING +camp, +four-week, -five, -four, -no, -o'clock, -wait, lost 'five', lost 'wait', negation differs, numbers differ |
| t5-small-synth+guard@rules | Meet me at four no wait five o'clock. |  |
| t5-tiny+guard>punct-en+guard@rules | Meet me at four. No wait, five, o'clock. |  |
| t5-tiny | meet me at four no wait five o'clock. |  |
| t5-tiny+guard | Meet me at four no wait five o'clock. |  |
| t5-tiny@kroko+rules | Meet me at four no wait five o'clock. |  |
| t5-tiny+guard@kroko+rules | Meet me at four no wait five o'clock. |  |
| t5-tiny@rules#t2 | Meet me at four no wait five o'clock. |  |
| t5-tiny+guard@rules#t2 | Meet me at four no wait five o'clock. |  |
| t5-tiny@rules | Meet me at four no wait five o'clock. |  |
| t5-tiny+guard@rules | Meet me at four no wait five o'clock. |  |

### c01 (code)

| option | output | flag |
|---|---|---|
| ref | Run npm run build and then git rebase on main. |  |
| (raw words, untouched) | run npm run build and then git rebase on main |  |
| asr-kroko | Run NPM run build and then get rebase on main | MEANING +get, -git, lost 'git rebase' |
| asr-moonshine-base | Run and pm run build and then get rebase on main. | MEANING +get, +pm, -git, -npm, lost 'git rebase', lost 'npm run build' |
| asr-moonshine-tiny | Run npm run build and then get rebace on main. | MEANING +get, +rebace, -git, -rebase, lost 'git rebase' |
| lfm2.5-1.2b | Run npm run build then git rebase main | reworded -and, -on |
| lfm2.5-1.2b+guard | Run npm run build and then git rebase on main. |  |
| lfm2.5-1.2b@rules | Run npm run build then git rebase main | reworded -and, -on |
| lfm2.5-1.2b+guard@rules | Run npm run build and then git rebase on main. |  |
| punct-ct+guard@rules | Run npm run build and then git rebase on main. |  |
| punct-ct | run npm run build and then git rebase on main。 |  |
| punct-en+guard>t5-small-gec+guard@rules | Run Npm run build and then Git Rebase on main. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Run NPM, run, build and then get rebase on main. | MEANING +get, -git, lost 'git rebase' |
| punct-en+guard>t5-tiny+guard@rules#t2 | Run Npm run build and then Git Rebase on main. |  |
| punct-en+guard>t5-tiny+guard@rules | Run Npm run build and then Git Rebase on main. |  |
| punct-en+guard@kroko+rules | Run NPM, run, build and then get rebase on main. | MEANING +get, -git, lost 'git rebase' |
| punct-en+guard@rules#t2 | Run Npm run build and then Git Rebase on main. |  |
| punct-en+guard@rules | Run Npm run build and then Git Rebase on main. |  |
| punct-en | Run NPM run build and then Git Rebase on main |  |
| qwen2.5-0.5b | Run npm run build and then git rebase on main. |  |
| qwen2.5-0.5b+guard | Run npm run build and then git rebase on main. |  |
| qwen2.5-0.5b@kroko+rules | Run NPM run build, then get rebase on main. | MEANING +get, -git, lost 'git rebase' |
| qwen2.5-0.5b+guard@kroko+rules | Run NPM run build, and then get rebase on main. | MEANING +get, -git, lost 'git rebase' |
| qwen2.5-0.5b@rules#t2 | Run npm run build and then git rebase on main. |  |
| qwen2.5-0.5b+guard@rules#t2 | Run npm run build and then git rebase on main. |  |
| qwen2.5-0.5b@rules | Run npm run build and then git rebase on main. |  |
| qwen2.5-0.5b+guard@rules | Run npm run build and then git rebase on main. |  |
| qwen3-0.6b | Run npm run build and then git rebase on main. |  |
| qwen3-0.6b+guard | Run npm run build and then git rebase on main. |  |
| qwen3-0.6b@rules | Run npm run build and then git rebase on main. |  |
| qwen3-0.6b+guard@rules | Run npm run build and then git rebase on main. |  |
| rules+ | Run npm run build and then git rebase on main. |  |
| rules+@kroko+rules | Run NPM run build and then get rebase on main. | MEANING +get, -git, lost 'git rebase' |
| rules+@kroko | Run NPM run build and then get rebase on main. | MEANING +get, -git, lost 'git rebase' |
| rules-seam | Run npm run build and then git rebase on main |  |
| rules-seam@kroko | Run NPM run build and then get rebase on main | MEANING +get, -git, lost 'git rebase' |
| t5-base | Run npm run build and then git rebase on main. |  |
| t5-base+guard | Run npm run build and then git rebase on main. |  |
| t5-base@kroko+rules | Run NPM run build and then get rebase on main. | MEANING +get, -git, lost 'git rebase' |
| t5-base+guard@kroko+rules | Run NPM run build and then get rebase on main. | MEANING +get, -git, lost 'git rebase' |
| t5-base@rules | Run npm run build and then git rebase on main. |  |
| t5-base+guard@rules | Run npm run build and then git rebase on main. |  |
| t5-mini | run npm run build and then git rebase on main. |  |
| t5-mini+guard | Run npm run build and then git rebase on main. |  |
| t5-mini@rules#t2 | Run npm run build and then git rebase on the main | reworded +the |
| t5-mini+guard@rules#t2 | Run npm run build and then git rebase on main. |  |
| t5-mini@rules | Run npm run build and then git rebase on the main | reworded +the |
| t5-mini+guard@rules | Run npm run build and then git rebase on main. |  |
| t5-small-gec | run npm run build and then git rebase on main |  |
| t5-small-gec+guard | Run npm run build and then git rebase on main. |  |
| t5-small-gec@kroko+rules | Run NPM run build and then get rebase on main | MEANING +get, -git, lost 'git rebase' |
| t5-small-gec+guard@kroko+rules | Run NPM run build and then get rebase on main. | MEANING +get, -git, lost 'git rebase' |
| t5-small-gec@rules#t2 | Run npm run build and then git rebase on main |  |
| t5-small-gec+guard@rules#t2 | Run npm run build and then git rebase on main. |  |
| t5-small-gec@rules | Run npm run build and then git rebase on main |  |
| t5-small-gec+guard@rules | Run npm run build and then git rebase on main. |  |
| t5-small-synth | run npm and build a new clone on main npm. | MEANING +clone, +new, -git, -rebase, -run, lost 'git rebase', lost 'npm run build' |
| t5-small-synth+guard | Run npm run build and then git rebase on main. |  |
| t5-small-synth@rules | Open a new machine and then create a new tree. | MEANING +create, +machine, +new, +open, +tree, -build, -git, -main, -npm, -rebase, -run, lost 'git rebase', lost 'main', lost 'npm run build' |
| t5-small-synth+guard@rules | Run npm run build and then git rebase on main. |  |
| t5-tiny+guard>punct-en+guard@rules | Run Npm run build and then Git Rebase on Main. |  |
| t5-tiny | run npm run build and then git rebase on the main | reworded +the |
| t5-tiny+guard | Run npm run build and then git rebase on main. |  |
| t5-tiny@kroko+rules | Run NPM run and run then get rebase on the main. | MEANING +get, -build, -git, lost 'git rebase', lost 'npm run build' |
| t5-tiny+guard@kroko+rules | Run NPM run build and then get rebase on main. | MEANING +get, -git, lost 'git rebase' |
| t5-tiny@rules#t2 | Run npm run build and then git rebase on the main | reworded +the |
| t5-tiny+guard@rules#t2 | Run npm run build and then git rebase on main. |  |
| t5-tiny@rules | Run npm run build and then git rebase on the main | reworded +the |
| t5-tiny+guard@rules | Run npm run build and then git rebase on main. |  |

### c02 (code)

| option | output | flag |
|---|---|---|
| ref | Rename the variable user_id to account_id in src/main.ts. |  |
| (raw words, untouched) | rename the variable user_id to account_id in src/main.ts |  |
| asr-kroko | Rename the variable user ID to account ID in SRC/main.ts | MEANING +account, +id, +user, -account_id, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| asr-moonshine-base | Rename the variable user id to account id in src/main.ts. | MEANING +account, +id, +user, -account_id, -user_id, lost 'account_id', lost 'user_id' |
| asr-moonshine-tiny | Rename the variable user ID to account ID and src/main.ts. | MEANING +account, +id, +user, -account_id, -user_id, lost 'account_id', lost 'user_id' |
| lfm2.5-1.2b | The variable user_id should be renamed to account_id in src/main.ts | MEANING +renamed, -rename |
| lfm2.5-1.2b+guard | Rename The variable user_id to account_id in src/main.ts. |  |
| lfm2.5-1.2b@rules | I renamed the variable user_id to account_id in src/main.ts | MEANING +renamed, -rename |
| lfm2.5-1.2b+guard@rules | Rename the variable user_id to account_id in src/main.ts. |  |
| punct-ct+guard@rules | Rename the variable user_id to account_id in src/main.ts. |  |
| punct-ct | rename the variable user _ id to account _ id in src / main . ts。 | MEANING +_, +account, +id, +main, +src, +ts, +user, -account_id, -src/main.ts, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| punct-en+guard>t5-small-gec+guard@rules | Rename, the variable user_id to account_id in src/main.ts. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Rename the variable user ID to account ID in SRC/main.ts. | MEANING +account, +id, +user, -account_id, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| punct-en+guard>t5-tiny+guard@rules#t2 | Rename, the variable user_id to account_id in src/main.ts. |  |
| punct-en+guard>t5-tiny+guard@rules | Rename, the variable user_id to account_id in src/main.ts. |  |
| punct-en+guard@kroko+rules | Rename the variable user ID to account ID in SRC/main.ts. | MEANING +account, +id, +user, -account_id, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| punct-en+guard@rules#t2 | Rename, the variable user_id to account_id in src/main.ts. |  |
| punct-en+guard@rules | Rename, the variable user_id to account_id in src/main.ts. |  |
| punct-en | Rename, the variable user_id to account_id in src/main.ts, |  |
| qwen2.5-0.5b | rename the variable user_id to account_id in src/main.ts |  |
| qwen2.5-0.5b+guard | Rename the variable user_id to account_id in src/main.ts. |  |
| qwen2.5-0.5b@kroko+rules | Rename the variable user ID to account ID in SRC/main.ts | MEANING +account, +id, +user, -account_id, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| qwen2.5-0.5b+guard@kroko+rules | Rename the variable user ID to account ID in SRC/main.ts. | MEANING +account, +id, +user, -account_id, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| qwen2.5-0.5b@rules#t2 | Rename the variable user_id to account_id in src/main.ts |  |
| qwen2.5-0.5b+guard@rules#t2 | Rename the variable user_id to account_id in src/main.ts. |  |
| qwen2.5-0.5b@rules | Rename the variable user_id to account_id in src/main.ts |  |
| qwen2.5-0.5b+guard@rules | Rename the variable user_id to account_id in src/main.ts. |  |
| qwen3-0.6b | rename the variable user_id to account_id in src/main.ts |  |
| qwen3-0.6b+guard | Rename the variable user_id to account_id in src/main.ts. |  |
| qwen3-0.6b@rules | Rename the variable user_id to account_id in src/main.ts. |  |
| qwen3-0.6b+guard@rules | Rename the variable user_id to account_id in src/main.ts. |  |
| rules+ | Rename the variable user_id to account_id in src/main.ts. |  |
| rules+@kroko+rules | Rename the variable user ID to account ID in SRC/main.ts. | MEANING +account, +id, +user, -account_id, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| rules+@kroko | Rename the variable user ID to account ID in SRC/main.ts. | MEANING +account, +id, +user, -account_id, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| rules-seam | Rename the variable user_id to account_id in src/main.ts |  |
| rules-seam@kroko | Rename the variable user ID to account ID in SRC/main.ts | MEANING +account, +id, +user, -account_id, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| t5-base | rename the variable user_id to account_id in src/main.ts. |  |
| t5-base+guard | Rename the variable user_id to account_id in src/main.ts. |  |
| t5-base@kroko+rules | Rename the variable user ID to account ID in SRC/main.ts. | MEANING +account, +id, +user, -account_id, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| t5-base+guard@kroko+rules | Rename the variable user ID to account ID in SRC/main.ts. | MEANING +account, +id, +user, -account_id, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| t5-base@rules | Rename the variable user_id to account_id in src/main.ts. |  |
| t5-base+guard@rules | Rename the variable user_id to account_id in src/main.ts. |  |
| t5-mini | rename the variable user _ id to account _ id in the srclmaints | MEANING +_, +account, +id, +srclmaints, +user, -account_id, -src/main.ts, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| t5-mini+guard | Rename the variable user_id to account_id in src/main.ts. |  |
| t5-mini@rules#t2 | Rename the variable user _ id to account _ id in the srclmaints. | MEANING +_, +account, +id, +srclmaints, +user, -account_id, -src/main.ts, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| t5-mini+guard@rules#t2 | Rename the variable user_id to account_id in src/main.ts. |  |
| t5-mini@rules | Rename the variable user _ id to account _ id in the srclmaints. | MEANING +_, +account, +id, +srclmaints, +user, -account_id, -src/main.ts, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| t5-mini+guard@rules | Rename the variable user_id to account_id in src/main.ts. |  |
| t5-small-gec | rename the variable user _ id to account _ id in src / main. ts | MEANING +_, +account, +id, +main, +src, +ts, +user, -account_id, -src/main.ts, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| t5-small-gec+guard | Rename the variable user_id to account_id in src/main.ts. |  |
| t5-small-gec@kroko+rules | Rename the variable user ID to account ID in SRC / main. ts | MEANING +account, +id, +main, +src, +ts, +user, -account_id, -src/main.ts, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| t5-small-gec+guard@kroko+rules | Rename the variable user ID to account ID in SRC/main.ts. | MEANING +account, +id, +user, -account_id, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| t5-small-gec@rules#t2 | Rename the variable user _ id to account _ id in src / main. ts | MEANING +_, +account, +id, +main, +src, +ts, +user, -account_id, -src/main.ts, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| t5-small-gec+guard@rules#t2 | Rename the variable user_id to account_id in src/main.ts. |  |
| t5-small-gec@rules | Rename the variable user _ id to account _ id in src / main. ts | MEANING +_, +account, +id, +main, +src, +ts, +user, -account_id, -src/main.ts, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| t5-small-gec+guard@rules | Rename the variable user_id to account_id in src/main.ts. |  |
| t5-small-synth | rename the variable user_to_to_success_in s/maints_. | MEANING +s/maints_, +user_to_to_success_in, -account_id, -src/main.ts, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| t5-small-synth+guard | Rename the variable user_id to account_id in src/main.ts. |  |
| t5-small-synth@rules | Rename the variable_to account_in src/maints. | MEANING +account_in, +src/maints, +variable_to, -account_id, -src/main.ts, -user_id, -variable, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| t5-small-synth+guard@rules | Rename the variable user_id to account_id in src/main.ts. |  |
| t5-tiny+guard>punct-en+guard@rules | Rename, the variable user_id to account_id in Src/main.ts. | MEANING lost 'src/main.ts' |
| t5-tiny | rename the variable user _ id to account _ id in the scripts. | MEANING +_, +account, +id, +scripts, +user, -account_id, -src/main.ts, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| t5-tiny+guard | Rename the variable user_id to account_id in src/main.ts. |  |
| t5-tiny@kroko+rules | Rename the variable user ID to account ID in SRCmainments | MEANING +account, +id, +srcmainments, +user, -account_id, -src/main.ts, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| t5-tiny+guard@kroko+rules | Rename the variable user ID to account ID in SRC/main.ts. | MEANING +account, +id, +user, -account_id, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| t5-tiny@rules#t2 | Rename the variable user _id to account _id in the scripts. | MEANING +_id, +account, +scripts, +user, -account_id, -src/main.ts, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| t5-tiny+guard@rules#t2 | Rename the variable user_id to account_id in src/main.ts. |  |
| t5-tiny@rules | Rename the variable user _id to account _id in the scripts. | MEANING +_id, +account, +scripts, +user, -account_id, -src/main.ts, -user_id, lost 'account_id', lost 'src/main.ts', lost 'user_id' |
| t5-tiny+guard@rules | Rename the variable user_id to account_id in src/main.ts. |  |

### c03 (code)

| option | output | flag |
|---|---|---|
| ref | The useEffect hook runs twice in strict mode. |  |
| (raw words, untouched) | the useEffect hook runs twice in strict mode |  |
| asr-kroko | The use effect hook runs twice in strict mode | MEANING +effect, +use, -useeffect, lost 'useEffect' |
| asr-moonshine-base | The use effect hook runs twice in strict mode. | MEANING +effect, +use, -useeffect, lost 'useEffect' |
| asr-moonshine-tiny | The use effect hook runs twice in strict mode. | MEANING +effect, +use, -useeffect, lost 'useEffect' |
| lfm2.5-1.2b | The useEffect hook runs twice in strict mode |  |
| lfm2.5-1.2b+guard | The useEffect hook runs twice in strict mode. |  |
| lfm2.5-1.2b@rules | The speech recognizer misheard "useEffect" as "the useEffect" and confused it with "the" and "you're". | MEANING +confused, +misheard, +recognizer, +speech, -hook, -mode, -runs, -strict, -twice, lost 'twice', numbers differ |
| lfm2.5-1.2b+guard@rules | "The useEffect" hook runs twice in strict mode. |  |
| punct-ct+guard@rules | The useEffect hook runs twice in strict mode. |  |
| punct-ct | the useEffect hook runs twice in strict mode。 |  |
| punct-en+guard>t5-small-gec+guard@rules | The useEffect hook runs twice in strict mode. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | The use effect hook runs twice in strict mode. | MEANING +effect, +use, -useeffect, lost 'useEffect' |
| punct-en+guard>t5-tiny+guard@rules#t2 | The useEffect hook runs twice in strict mode. |  |
| punct-en+guard>t5-tiny+guard@rules | The useEffect hook runs twice in strict mode. |  |
| punct-en+guard@kroko+rules | The use effect hook runs twice in strict mode. | MEANING +effect, +use, -useeffect, lost 'useEffect' |
| punct-en+guard@rules#t2 | The useEffect hook runs twice in strict mode. |  |
| punct-en+guard@rules | The useEffect hook runs twice in strict mode. |  |
| punct-en | The useEffect hook runs twice in strict mode |  |
| qwen2.5-0.5b | The useEffect hook runs twice in strict mode. |  |
| qwen2.5-0.5b+guard | The useEffect hook runs twice in strict mode. |  |
| qwen2.5-0.5b@kroko+rules | The use effect hook runs twice in strict mode. | MEANING +effect, +use, -useeffect, lost 'useEffect' |
| qwen2.5-0.5b+guard@kroko+rules | The use effect hook runs twice in strict mode. | MEANING +effect, +use, -useeffect, lost 'useEffect' |
| qwen2.5-0.5b@rules#t2 | The useEffect hook runs twice in strict mode. |  |
| qwen2.5-0.5b+guard@rules#t2 | The useEffect hook runs twice in strict mode. |  |
| qwen2.5-0.5b@rules | The useEffect hook runs twice in strict mode. |  |
| qwen2.5-0.5b+guard@rules | The useEffect hook runs twice in strict mode. |  |
| qwen3-0.6b | The useEffect hook runs twice in strict mode. |  |
| qwen3-0.6b+guard | The useEffect hook runs twice in strict mode. |  |
| qwen3-0.6b@rules | The useEffect hook runs twice in strict mode. |  |
| qwen3-0.6b+guard@rules | The useEffect hook runs twice in strict mode. |  |
| rules+ | The useEffect hook runs twice in strict mode. |  |
| rules+@kroko+rules | The use effect hook runs twice in strict mode. | MEANING +effect, +use, -useeffect, lost 'useEffect' |
| rules+@kroko | The use effect hook runs twice in strict mode. | MEANING +effect, +use, -useeffect, lost 'useEffect' |
| rules-seam | The useEffect hook runs twice in strict mode |  |
| rules-seam@kroko | The use effect hook runs twice in strict mode | MEANING +effect, +use, -useeffect, lost 'useEffect' |
| t5-base | The useEffect hook runs twice in strict mode. |  |
| t5-base+guard | The useEffect hook runs twice in strict mode. |  |
| t5-base@kroko+rules | The use effect hook runs twice in strict mode. | MEANING +effect, +use, -useeffect, lost 'useEffect' |
| t5-base+guard@kroko+rules | The use effect hook runs twice in strict mode. | MEANING +effect, +use, -useeffect, lost 'useEffect' |
| t5-base@rules | The useEffect hook runs twice in strict mode. |  |
| t5-base+guard@rules | The useEffect hook runs twice in strict mode. |  |
| t5-mini | The useeffect hook runs twice in strict mode. | MEANING lost 'useEffect' |
| t5-mini+guard | The useEffect hook runs twice in strict mode. |  |
| t5-mini@rules#t2 | The useeffect hook runs twice in strict mode. | MEANING lost 'useEffect' |
| t5-mini+guard@rules#t2 | The useEffect hook runs twice in strict mode. |  |
| t5-mini@rules | The useeffect hook runs twice in strict mode. | MEANING lost 'useEffect' |
| t5-mini+guard@rules | The useEffect hook runs twice in strict mode. |  |
| t5-small-gec | The useEffect hook runs twice in strict mode |  |
| t5-small-gec+guard | The useEffect hook runs twice in strict mode. |  |
| t5-small-gec@kroko+rules | The use effect hook runs twice in strict mode | MEANING +effect, +use, -useeffect, lost 'useEffect' |
| t5-small-gec+guard@kroko+rules | The use effect hook runs twice in strict mode. | MEANING +effect, +use, -useeffect, lost 'useEffect' |
| t5-small-gec@rules#t2 | The useEffect hook runs twice in strict mode |  |
| t5-small-gec+guard@rules#t2 | The useEffect hook runs twice in strict mode. |  |
| t5-small-gec@rules | The useEffect hook runs twice in strict mode |  |
| t5-small-gec+guard@rules | The useEffect hook runs twice in strict mode. |  |
| t5-small-synth | the effect of looping is twice as harsh as in a normal mode. | MEANING +effect, +harsh, +looping, +normal, -hook, -runs, -strict, -useeffect, lost 'useEffect' |
| t5-small-synth+guard | The useEffect hook runs twice in strict mode. |  |
| t5-small-synth@rules | The effect of a loop is a continuous loop that runs through the tree. | MEANING +continuous, +effect, +loop, +through, +tree, -hook, -mode, -strict, -twice, -useeffect, lost 'twice', lost 'useEffect', numbers differ |
| t5-small-synth+guard@rules | The useEffect hook runs twice in strict mode. |  |
| t5-tiny+guard>punct-en+guard@rules | The useEffect hook runs twice in strict mode. |  |
| t5-tiny | The perfect hook runs twice in strict mode. | MEANING +perfect, -useeffect, lost 'useEffect' |
| t5-tiny+guard | The useEffect hook runs twice in strict mode. |  |
| t5-tiny@kroko+rules | The use effect hook runs twice in strict mode. | MEANING +effect, +use, -useeffect, lost 'useEffect' |
| t5-tiny+guard@kroko+rules | The use effect hook runs twice in strict mode. | MEANING +effect, +use, -useeffect, lost 'useEffect' |
| t5-tiny@rules#t2 | The perfect hook runs twice in strict mode. | MEANING +perfect, -useeffect, lost 'useEffect' |
| t5-tiny+guard@rules#t2 | The useEffect hook runs twice in strict mode. |  |
| t5-tiny@rules | The perfect hook runs twice in strict mode. | MEANING +perfect, -useeffect, lost 'useEffect' |
| t5-tiny+guard@rules | The useEffect hook runs twice in strict mode. |  |

### c04 (code)

| option | output | flag |
|---|---|---|
| ref | Open localhost:8080 and check the kubectl logs. |  |
| (raw words, untouched) | open localhost:8080 and check the kubectl logs |  |
| asr-kroko | Open localhost colon eight thousand and eighty and check the cubeal logs | MEANING +colon, +cubeal, +eight, +eighty, +localhost, +thousand, -kubectl, -localhost:8080, lost 'kubectl', lost 'localhost:8080', numbers differ |
| asr-moonshine-base | Open localhost:8080 and check the cubectle logs. | MEANING +cubectle, -kubectl, lost 'kubectl' |
| asr-moonshine-tiny | Open localhost colon 800080 and check the cubectal logs. | MEANING +800080, +colon, +cubectal, +localhost, -kubectl, -localhost:8080, lost 'kubectl', lost 'localhost:8080', numbers differ |
| lfm2.5-1.2b | open localhost:8080 and check the kubectl logs |  |
| lfm2.5-1.2b+guard | Open localhost:8080 and check the kubectl logs. |  |
| lfm2.5-1.2b@rules | Open localhost:8080 and check the kubectl logs |  |
| lfm2.5-1.2b+guard@rules | Open localhost:8080 and check the kubectl logs. |  |
| punct-ct+guard@rules | Open localhost:8080 and check the kubectl logs. |  |
| punct-ct | open localhost : 8080 and check the kubectl logs。 | MEANING +8080, +localhost, -localhost:8080, lost 'localhost:8080' |
| punct-en+guard>t5-small-gec+guard@rules | Open localhost:8080 and check the kubectl logs. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Open localhost, colon eight thousand and eighty, and check the cubeal logs. | MEANING +colon, +cubeal, +eight, +eighty, +localhost, +thousand, -kubectl, -localhost:8080, lost 'kubectl', lost 'localhost:8080', numbers differ |
| punct-en+guard>t5-tiny+guard@rules#t2 | Open localhost:8080 and check the kubectl logs. |  |
| punct-en+guard>t5-tiny+guard@rules | Open localhost:8080 and check the kubectl logs. |  |
| punct-en+guard@kroko+rules | Open localhost, colon eight thousand and eighty, and check the cubeal logs. | MEANING +colon, +cubeal, +eight, +eighty, +localhost, +thousand, -kubectl, -localhost:8080, lost 'kubectl', lost 'localhost:8080', numbers differ |
| punct-en+guard@rules#t2 | Open localhost:8080 and check the kubectl logs. |  |
| punct-en+guard@rules | Open localhost:8080 and check the kubectl logs. |  |
| punct-en | Open localhost:8080 and check the kubectl logs. |  |
| qwen2.5-0.5b | Open localhost:8080 and check the kubectl logs. |  |
| qwen2.5-0.5b+guard | Open localhost:8080 and check the kubectl logs. |  |
| qwen2.5-0.5b@kroko+rules | Open localhost:8000 and check the cubeal logs. | MEANING +cubeal, +localhost:8000, -kubectl, -localhost:8080, lost 'kubectl', lost 'localhost:8080', numbers differ |
| qwen2.5-0.5b+guard@kroko+rules | Open localhost colon eight thousand and eighty and check the cubeal logs. | MEANING +colon, +cubeal, +eight, +eighty, +localhost, +thousand, -kubectl, -localhost:8080, lost 'kubectl', lost 'localhost:8080', numbers differ |
| qwen2.5-0.5b@rules#t2 | Open localhost:8080 and check the kubectl logs. |  |
| qwen2.5-0.5b+guard@rules#t2 | Open localhost:8080 and check the kubectl logs. |  |
| qwen2.5-0.5b@rules | Open localhost:8080 and check the kubectl logs. |  |
| qwen2.5-0.5b+guard@rules | Open localhost:8080 and check the kubectl logs. |  |
| qwen3-0.6b | Open localhost:8080 and check the kubectl logs. |  |
| qwen3-0.6b+guard | Open localhost:8080 and check the kubectl logs. |  |
| qwen3-0.6b@rules | Open localhost:8080 and check the kubectl logs. |  |
| qwen3-0.6b+guard@rules | Open localhost:8080 and check the kubectl logs. |  |
| rules+ | Open localhost:8080 and check the kubectl logs. |  |
| rules+@kroko+rules | Open localhost colon eight thousand and eighty and check the cubeal logs. | MEANING +colon, +cubeal, +eight, +eighty, +localhost, +thousand, -kubectl, -localhost:8080, lost 'kubectl', lost 'localhost:8080', numbers differ |
| rules+@kroko | Open localhost colon eight thousand and eighty and check the cubeal logs. | MEANING +colon, +cubeal, +eight, +eighty, +localhost, +thousand, -kubectl, -localhost:8080, lost 'kubectl', lost 'localhost:8080', numbers differ |
| rules-seam | Open localhost:8080 and check the kubectl logs |  |
| rules-seam@kroko | Open localhost colon eight thousand and eighty and check the cubeal logs | MEANING +colon, +cubeal, +eight, +eighty, +localhost, +thousand, -kubectl, -localhost:8080, lost 'kubectl', lost 'localhost:8080', numbers differ |
| t5-base | Open localhost:8080 and check the kubectl logs. |  |
| t5-base+guard | Open localhost:8080 and check the kubectl logs. |  |
| t5-base@kroko+rules | Open localhost colon eight thousand and eighty and check the cubeal logs. | MEANING +colon, +cubeal, +eight, +eighty, +localhost, +thousand, -kubectl, -localhost:8080, lost 'kubectl', lost 'localhost:8080', numbers differ |
| t5-base+guard@kroko+rules | Open localhost colon eight thousand and eighty and check the cubeal logs. | MEANING +colon, +cubeal, +eight, +eighty, +localhost, +thousand, -kubectl, -localhost:8080, lost 'kubectl', lost 'localhost:8080', numbers differ |
| t5-base@rules | Open localhost:8080 and check the kubectl logs. |  |
| t5-base+guard@rules | Open localhost:8080 and check the kubectl logs. |  |
| t5-mini | open localhost :8080 and check the object logs. | MEANING +8080, +localhost, +object, -kubectl, -localhost:8080, lost 'kubectl', lost 'localhost:8080' |
| t5-mini+guard | Open localhost:8080 and check the kubectl logs. |  |
| t5-mini@rules#t2 | Open localhost :8080 and check the object logs. | MEANING +8080, +localhost, +object, -kubectl, -localhost:8080, lost 'kubectl', lost 'localhost:8080' |
| t5-mini+guard@rules#t2 | Open localhost:8080 and check the kubectl logs. |  |
| t5-mini@rules | Open localhost :8080 and check the object logs. | MEANING +8080, +localhost, +object, -kubectl, -localhost:8080, lost 'kubectl', lost 'localhost:8080' |
| t5-mini+guard@rules | Open localhost:8080 and check the kubectl logs. |  |
| t5-small-gec | open localhost :8080 and check the kubectl logs | MEANING +8080, +localhost, -localhost:8080, lost 'localhost:8080' |
| t5-small-gec+guard | Open localhost:8080 and check the kubectl logs. |  |
| t5-small-gec@kroko+rules | Open localhost colon eight thousand and eighty and check the cubeal logs | MEANING +colon, +cubeal, +eight, +eighty, +localhost, +thousand, -kubectl, -localhost:8080, lost 'kubectl', lost 'localhost:8080', numbers differ |
| t5-small-gec+guard@kroko+rules | Open localhost colon eight thousand and eighty and check the cubeal logs. | MEANING +colon, +cubeal, +eight, +eighty, +localhost, +thousand, -kubectl, -localhost:8080, lost 'kubectl', lost 'localhost:8080', numbers differ |
| t5-small-gec@rules#t2 | Open localhost :8080 and check the kubectl logs | MEANING +8080, +localhost, -localhost:8080, lost 'localhost:8080' |
| t5-small-gec+guard@rules#t2 | Open localhost:8080 and check the kubectl logs. |  |
| t5-small-gec@rules | Open localhost :8080 and check the kubectl logs | MEANING +8080, +localhost, -localhost:8080, lost 'localhost:8080' |
| t5-small-gec+guard@rules | Open localhost:8080 and check the kubectl logs. |  |
| t5-small-synth | Open the local :8080 and check the kbec huts. | MEANING +8080, +huts, +kbec, +local, -kubectl, -localhost:8080, -logs, lost 'kubectl', lost 'localhost:8080' |
| t5-small-synth+guard | Open localhost:8080 and check the kubectl logs. |  |
| t5-small-synth@rules | Open local time: 9:30 am - check the digits. | MEANING +9:30, +digits, +local, +time, -kubectl, -localhost:8080, -logs, lost 'kubectl', lost 'localhost:8080', numbers differ |
| t5-small-synth+guard@rules | Open localhost:8080 and check the kubectl logs. |  |
| t5-tiny+guard>punct-en+guard@rules | Open localhost:8080 and check the kubectl logs. |  |
| t5-tiny | open localhost :8080 and check the robot logs. | MEANING +8080, +localhost, +robot, -kubectl, -localhost:8080, lost 'kubectl', lost 'localhost:8080' |
| t5-tiny+guard | Open localhost:8080 and check the kubectl logs. |  |
| t5-tiny@kroko+rules | Open localhost colon eight thousand and eighty and check the cubeal logs. | MEANING +colon, +cubeal, +eight, +eighty, +localhost, +thousand, -kubectl, -localhost:8080, lost 'kubectl', lost 'localhost:8080', numbers differ |
| t5-tiny+guard@kroko+rules | Open localhost colon eight thousand and eighty and check the cubeal logs. | MEANING +colon, +cubeal, +eight, +eighty, +localhost, +thousand, -kubectl, -localhost:8080, lost 'kubectl', lost 'localhost:8080', numbers differ |
| t5-tiny@rules#t2 | Open localhost :8080 and check the robot logs. | MEANING +8080, +localhost, +robot, -kubectl, -localhost:8080, lost 'kubectl', lost 'localhost:8080' |
| t5-tiny+guard@rules#t2 | Open localhost:8080 and check the kubectl logs. |  |
| t5-tiny@rules | Open localhost :8080 and check the robot logs. | MEANING +8080, +localhost, +robot, -kubectl, -localhost:8080, lost 'kubectl', lost 'localhost:8080' |
| t5-tiny+guard@rules | Open localhost:8080 and check the kubectl logs. |  |

### m01 (meaning)

| option | output | flag |
|---|---|---|
| ref | I never said she stole the money. |  |
| (raw words, untouched) | i never said she stole the money |  |
| asr-kroko | I never said she stole the money |  |
| asr-moonshine-base | I never said she stole the money |  |
| asr-moonshine-tiny | I never said she stole the money. |  |
| lfm2.5-1.2b | I never said she stole the money. |  |
| lfm2.5-1.2b+guard | I never said she stole the money. |  |
| lfm2.5-1.2b@rules | I didn't say she stole the money. | MEANING +didn't, +say, -never, -said, lost 'never', negation differs |
| lfm2.5-1.2b+guard@rules | I never said she stole the money. |  |
| punct-ct+guard@rules | I never said she stole the money. |  |
| punct-ct | i never said she stole the money。 |  |
| punct-en+guard>t5-small-gec+guard@rules | I never said she stole the money. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | I never said she stole the money. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | I never said she stole the money. |  |
| punct-en+guard>t5-tiny+guard@rules | I never said she stole the money. |  |
| punct-en+guard@kroko+rules | I never said she stole the money. |  |
| punct-en+guard@rules#t2 | I never said she stole the money. |  |
| punct-en+guard@rules | I never said she stole the money. |  |
| punct-en | I never said she stole the money |  |
| qwen2.5-0.5b | I never said she stole the money. |  |
| qwen2.5-0.5b+guard | I never said she stole the money. |  |
| qwen2.5-0.5b@kroko+rules | I never said she stole the money. |  |
| qwen2.5-0.5b+guard@kroko+rules | I never said she stole the money. |  |
| qwen2.5-0.5b@rules#t2 | I never said she stole the money. |  |
| qwen2.5-0.5b+guard@rules#t2 | I never said she stole the money. |  |
| qwen2.5-0.5b@rules | I never said she stole the money. |  |
| qwen2.5-0.5b+guard@rules | I never said she stole the money. |  |
| qwen3-0.6b | I never said she stole the money. |  |
| qwen3-0.6b+guard | I never said she stole the money. |  |
| qwen3-0.6b@rules | I never said she stole the money. |  |
| qwen3-0.6b+guard@rules | I never said she stole the money. |  |
| rules+ | I never said she stole the money. |  |
| rules+@kroko+rules | I never said she stole the money. |  |
| rules+@kroko | I never said she stole the money. |  |
| rules-seam | I never said she stole the money |  |
| rules-seam@kroko | I never said she stole the money |  |
| t5-base | I never said she stole the money. |  |
| t5-base+guard | I never said she stole the money. |  |
| t5-base@kroko+rules | I never said she stole the money. |  |
| t5-base+guard@kroko+rules | I never said she stole the money. |  |
| t5-base@rules | I never said she stole the money. |  |
| t5-base+guard@rules | I never said she stole the money. |  |
| t5-mini | I never said she stole the money. |  |
| t5-mini+guard | I never said she stole the money. |  |
| t5-mini@rules#t2 | I never said she stole the money. |  |
| t5-mini+guard@rules#t2 | I never said she stole the money. |  |
| t5-mini@rules | I never said she stole the money. |  |
| t5-mini+guard@rules | I never said she stole the money. |  |
| t5-small-gec | I never said she stole the money. |  |
| t5-small-gec+guard | I never said she stole the money. |  |
| t5-small-gec@kroko+rules | I never said she stole the money. |  |
| t5-small-gec+guard@kroko+rules | I never said she stole the money. |  |
| t5-small-gec@rules#t2 | I never said she stole the money. |  |
| t5-small-gec+guard@rules#t2 | I never said she stole the money. |  |
| t5-small-gec@rules | I never said she stole the money. |  |
| t5-small-gec+guard@rules | I never said she stole the money. |  |
| t5-small-synth | I never said she won the lottery. | MEANING +lottery, +won, -money, -stole, lost 'stole' |
| t5-small-synth+guard | I never said she stole the money. |  |
| t5-small-synth@rules | I never said she stole the money. |  |
| t5-small-synth+guard@rules | I never said she stole the money. |  |
| t5-tiny+guard>punct-en+guard@rules | I never said she stole the money. |  |
| t5-tiny | I never said she stole the money. |  |
| t5-tiny+guard | I never said she stole the money. |  |
| t5-tiny@kroko+rules | I never said she stole the money. |  |
| t5-tiny+guard@kroko+rules | I never said she stole the money. |  |
| t5-tiny@rules#t2 | I never said she stole the money. |  |
| t5-tiny+guard@rules#t2 | I never said she stole the money. |  |
| t5-tiny@rules | I never said she stole the money. |  |
| t5-tiny+guard@rules | I never said she stole the money. |  |

### m02 (meaning)

| option | output | flag |
|---|---|---|
| ref | Don't turn off the lights in the kitchen. |  |
| (raw words, untouched) | don't turn off the lights in the kitchen |  |
| asr-kroko | Don't turn off the lights in the kitchen |  |
| asr-moonshine-base | Don't turn off the lights in the kitchen. |  |
| asr-moonshine-tiny | Don't turn off the lights in the kitchen. |  |
| lfm2.5-1.2b | Don't turn off the lights in the kitchen. |  |
| lfm2.5-1.2b+guard | Don't turn off the lights in the kitchen. |  |
| lfm2.5-1.2b@rules | Don't turn off the lights in the kitchen |  |
| lfm2.5-1.2b+guard@rules | Don't turn off the lights in the kitchen. |  |
| punct-ct+guard@rules | Don't turn off the lights in the kitchen. |  |
| punct-ct | don't turn off the lights in the kitchen。 |  |
| punct-en+guard>t5-small-gec+guard@rules | Don't turn off the lights in the kitchen. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Don't turn off the lights in the kitchen. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | Don't turn off the lights in the kitchen. |  |
| punct-en+guard>t5-tiny+guard@rules | Don't turn off the lights in the kitchen. |  |
| punct-en+guard@kroko+rules | Don't turn off the lights in the kitchen. |  |
| punct-en+guard@rules#t2 | Don't turn off the lights in the kitchen. |  |
| punct-en+guard@rules | Don't turn off the lights in the kitchen. |  |
| punct-en | Don't turn off the lights in the kitchen |  |
| qwen2.5-0.5b | Don't turn off the lights in the kitchen. |  |
| qwen2.5-0.5b+guard | Don't turn off the lights in the kitchen. |  |
| qwen2.5-0.5b@kroko+rules | Don't turn off the lights in the kitchen. |  |
| qwen2.5-0.5b+guard@kroko+rules | Don't turn off the lights in the kitchen. |  |
| qwen2.5-0.5b@rules#t2 | Don't turn off the lights in the kitchen. |  |
| qwen2.5-0.5b+guard@rules#t2 | Don't turn off the lights in the kitchen. |  |
| qwen2.5-0.5b@rules | Don't turn off the lights in the kitchen. |  |
| qwen2.5-0.5b+guard@rules | Don't turn off the lights in the kitchen. |  |
| qwen3-0.6b | Don't turn off the lights in the kitchen. |  |
| qwen3-0.6b+guard | Don't turn off the lights in the kitchen. |  |
| qwen3-0.6b@rules | Don't turn off the lights in the kitchen. |  |
| qwen3-0.6b+guard@rules | Don't turn off the lights in the kitchen. |  |
| rules+ | Don't turn off the lights in the kitchen. |  |
| rules+@kroko+rules | Don't turn off the lights in the kitchen. |  |
| rules+@kroko | Don't turn off the lights in the kitchen. |  |
| rules-seam | Don't turn off the lights in the kitchen |  |
| rules-seam@kroko | Don't turn off the lights in the kitchen |  |
| t5-base | Don't turn off the lights in the kitchen. |  |
| t5-base+guard | Don't turn off the lights in the kitchen. |  |
| t5-base@kroko+rules | Don't turn off the lights in the kitchen. |  |
| t5-base+guard@kroko+rules | Don't turn off the lights in the kitchen. |  |
| t5-base@rules | Don't turn off the lights in the kitchen. |  |
| t5-base+guard@rules | Don't turn off the lights in the kitchen. |  |
| t5-mini | Don't turn off the lights in the kitchen. |  |
| t5-mini+guard | Don't turn off the lights in the kitchen. |  |
| t5-mini@rules#t2 | Don't turn off the lights in the kitchen. |  |
| t5-mini+guard@rules#t2 | Don't turn off the lights in the kitchen. |  |
| t5-mini@rules | Don't turn off the lights in the kitchen. |  |
| t5-mini+guard@rules | Don't turn off the lights in the kitchen. |  |
| t5-small-gec | Don't turn off the lights in the kitchen. |  |
| t5-small-gec+guard | Don't turn off the lights in the kitchen. |  |
| t5-small-gec@kroko+rules | Don't turn off the lights in the kitchen |  |
| t5-small-gec+guard@kroko+rules | Don't turn off the lights in the kitchen. |  |
| t5-small-gec@rules#t2 | Don't turn off the lights in the kitchen |  |
| t5-small-gec+guard@rules#t2 | Don't turn off the lights in the kitchen. |  |
| t5-small-gec@rules | Don't turn off the lights in the kitchen |  |
| t5-small-gec+guard@rules | Don't turn off the lights in the kitchen. |  |
| t5-small-synth | don't turn off the lights in the kitchen. |  |
| t5-small-synth+guard | Don't turn off the lights in the kitchen. |  |
| t5-small-synth@rules | Don't turn off the lights in the kitchen. |  |
| t5-small-synth+guard@rules | Don't turn off the lights in the kitchen. |  |
| t5-tiny+guard>punct-en+guard@rules | Don't turn off the lights in the kitchen. |  |
| t5-tiny | I don't turn off the lights in the kitchen. | reworded +i |
| t5-tiny+guard | Don't turn off the lights in the kitchen. |  |
| t5-tiny@kroko+rules | I don't turn off the lights in the kitchen. | reworded +i |
| t5-tiny+guard@kroko+rules | Don't turn off the lights in the kitchen. |  |
| t5-tiny@rules#t2 | I don't turn off the lights in the kitchen. | reworded +i |
| t5-tiny+guard@rules#t2 | Don't turn off the lights in the kitchen. |  |
| t5-tiny@rules | I don't turn off the lights in the kitchen. | reworded +i |
| t5-tiny+guard@rules | Don't turn off the lights in the kitchen. |  |

### m03 (meaning)

| option | output | flag |
|---|---|---|
| ref | I'm gonna grab lunch, wanna come? |  |
| (raw words, untouched) | i'm gonna grab lunch wanna come |  |
| asr-kroko | I'm gonna grab lunch when I come | MEANING +when, -wanna, lost 'wanna' |
| asr-moonshine-base | I'm going to grab lunch when I come. | MEANING +going, +when, -gonna, -wanna, lost 'gonna', lost 'wanna' |
| asr-moonshine-tiny | I'm going to grab lunch when I come. | MEANING +going, +when, -gonna, -wanna, lost 'gonna', lost 'wanna' |
| lfm2.5-1.2b | I'm gonna grab lunch wanna come. |  |
| lfm2.5-1.2b+guard | I'm gonna grab lunch wanna come. |  |
| lfm2.5-1.2b@rules | I'm gonna grab lunch wanna come |  |
| lfm2.5-1.2b+guard@rules | I'm gonna grab lunch wanna come. |  |
| punct-ct+guard@rules | I'm gonna grab lunch wanna come. |  |
| punct-ct | i'm gonna grab lunch wanna come。 |  |
| punct-en+guard>t5-small-gec+guard@rules | I'm gonna grab lunch, wanna, come. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | I'm gonna grab lunch when I come. | MEANING +when, -wanna, lost 'wanna' |
| punct-en+guard>t5-tiny+guard@rules#t2 | I'm gonna grab lunch, wanna, come. |  |
| punct-en+guard>t5-tiny+guard@rules | I'm gonna grab lunch, wanna, come. |  |
| punct-en+guard@kroko+rules | I'm gonna grab lunch when I come. | MEANING +when, -wanna, lost 'wanna' |
| punct-en+guard@rules#t2 | I'm gonna grab, lunch, wanna, come. |  |
| punct-en+guard@rules | I'm gonna grab, lunch, wanna, come. |  |
| punct-en | I'm gonna grab, lunch, wanna, come |  |
| qwen2.5-0.5b | I'm gonna grab lunch, wanna come? |  |
| qwen2.5-0.5b+guard | I'm gonna grab lunch, wanna come? |  |
| qwen2.5-0.5b@kroko+rules | I'm gonna grab lunch when I come. | MEANING +when, -wanna, lost 'wanna' |
| qwen2.5-0.5b+guard@kroko+rules | I'm gonna grab lunch when I come. | MEANING +when, -wanna, lost 'wanna' |
| qwen2.5-0.5b@rules#t2 | I'm gonna grab lunch, wanna come? |  |
| qwen2.5-0.5b+guard@rules#t2 | I'm gonna grab lunch, wanna come? |  |
| qwen2.5-0.5b@rules | I'm gonna grab lunch, wanna come? |  |
| qwen2.5-0.5b+guard@rules | I'm gonna grab lunch, wanna come? |  |
| qwen3-0.6b | I'm gonna grab lunch, wanna come. |  |
| qwen3-0.6b+guard | I'm gonna grab lunch, wanna come. |  |
| qwen3-0.6b@rules | I'm gonna grab lunch, wanna come. |  |
| qwen3-0.6b+guard@rules | I'm gonna grab lunch, wanna come. |  |
| rules+ | I'm gonna grab lunch wanna come. |  |
| rules+@kroko+rules | I'm gonna grab lunch when I come. | MEANING +when, -wanna, lost 'wanna' |
| rules+@kroko | I'm gonna grab lunch when I come. | MEANING +when, -wanna, lost 'wanna' |
| rules-seam | I'm gonna grab lunch wanna come |  |
| rules-seam@kroko | I'm gonna grab lunch when I come | MEANING +when, -wanna, lost 'wanna' |
| t5-base | I'm gonna grab lunch wanna come. |  |
| t5-base+guard | I'm gonna grab lunch wanna come. |  |
| t5-base@kroko+rules | I'm gonna grab lunch when I come. | MEANING +when, -wanna, lost 'wanna' |
| t5-base+guard@kroko+rules | I'm gonna grab lunch when I come. | MEANING +when, -wanna, lost 'wanna' |
| t5-base@rules | I'm gonna grab lunch wanna come. |  |
| t5-base+guard@rules | I'm gonna grab lunch wanna come. |  |
| t5-mini | I am going to grab lunch and wanna come. | MEANING +going, -gonna, -i'm, lost 'gonna' |
| t5-mini+guard | I'm gonna grab lunch wanna come. |  |
| t5-mini@rules#t2 | I am going to grab lunch and wanna come. | MEANING +going, -gonna, -i'm, lost 'gonna' |
| t5-mini+guard@rules#t2 | I'm gonna grab lunch wanna come. |  |
| t5-mini@rules | I am going to grab lunch and wanna come. | MEANING +going, -gonna, -i'm, lost 'gonna' |
| t5-mini+guard@rules | I'm gonna grab lunch wanna come. |  |
| t5-small-gec | I'm gonna grab lunch. I wanna come. | reworded +i |
| t5-small-gec+guard | I'm gonna grab lunch. wanna come. |  |
| t5-small-gec@kroko+rules | I'm gonna grab lunch when I come. | MEANING +when, -wanna, lost 'wanna' |
| t5-small-gec+guard@kroko+rules | I'm gonna grab lunch when I come. | MEANING +when, -wanna, lost 'wanna' |
| t5-small-gec@rules#t2 | I'm gonna grab lunch. Wanna come? |  |
| t5-small-gec+guard@rules#t2 | I'm gonna grab lunch. Wanna come? |  |
| t5-small-gec@rules | I'm gonna grab lunch. Wanna come? |  |
| t5-small-gec+guard@rules | I'm gonna grab lunch. Wanna come? |  |
| t5-small-synth | I'm going to grab lunch tonight. | MEANING +going, +tonight, -come, -gonna, -wanna, lost 'gonna', lost 'wanna' |
| t5-small-synth+guard | I'm gonna grab lunch wanna come. |  |
| t5-small-synth@rules | I'm going to grab lunch tonight. | MEANING +going, +tonight, -come, -gonna, -wanna, lost 'gonna', lost 'wanna' |
| t5-small-synth+guard@rules | I'm gonna grab lunch wanna come. |  |
| t5-tiny+guard>punct-en+guard@rules | I'm gonna grab lunch. wanna come. |  |
| t5-tiny | I am going to grab lunch and want to come. | MEANING +going, +want, -gonna, -i'm, -wanna, lost 'gonna', lost 'wanna' |
| t5-tiny+guard | I'm gonna grab lunch wanna come. |  |
| t5-tiny@kroko+rules | I am going to grab lunch when I come. | MEANING +going, +when, -gonna, -i'm, -wanna, lost 'gonna', lost 'wanna' |
| t5-tiny+guard@kroko+rules | I'm gonna grab lunch when I come. | MEANING +when, -wanna, lost 'wanna' |
| t5-tiny@rules#t2 | I wanna grab lunch. I wanna come. | MEANING -gonna, -i'm, lost 'gonna' |
| t5-tiny+guard@rules#t2 | I'm gonna grab lunch. wanna come. |  |
| t5-tiny@rules | I wanna grab lunch. I wanna come. | MEANING -gonna, -i'm, lost 'gonna' |
| t5-tiny+guard@rules | I'm gonna grab lunch. wanna come. |  |

### m04 (meaning)

| option | output | flag |
|---|---|---|
| ref | Let's eat, Grandma. |  |
| (raw words, untouched) | lets eat grandma |  |
| asr-kroko | Let's eat grandma |  |
| asr-moonshine-base | Let's eat grandma |  |
| asr-moonshine-tiny | Let's eat grandma |  |
| lfm2.5-1.2b | Let's eat grandma. |  |
| lfm2.5-1.2b+guard | Let's eat grandma. |  |
| lfm2.5-1.2b@rules | Let's eat grandma |  |
| lfm2.5-1.2b+guard@rules | Let's eat grandma. |  |
| punct-ct+guard@rules | Lets eat grandma. |  |
| punct-ct | lets eat grandma。 |  |
| punct-en+guard>t5-small-gec+guard@rules | Let's eat Grandma. |  |
| punct-en+guard>t5-tiny+guard@kroko+rules | Let's eat Grandma. |  |
| punct-en+guard>t5-tiny+guard@rules#t2 | Let's eat Grandma. |  |
| punct-en+guard>t5-tiny+guard@rules | Let's eat Grandma. |  |
| punct-en+guard@kroko+rules | Let's eat Grandma. |  |
| punct-en+guard@rules#t2 | Lets eat Grandma. |  |
| punct-en+guard@rules | Lets eat Grandma. |  |
| punct-en | Lets eat Grandma |  |
| qwen2.5-0.5b | Let's eat Grandma. |  |
| qwen2.5-0.5b+guard | Let's eat Grandma. |  |
| qwen2.5-0.5b@kroko+rules | Let's eat Grandma. |  |
| qwen2.5-0.5b+guard@kroko+rules | Let's eat Grandma. |  |
| qwen2.5-0.5b@rules#t2 | Let's eat Grandma. |  |
| qwen2.5-0.5b+guard@rules#t2 | Let's eat Grandma. |  |
| qwen2.5-0.5b@rules | Let's eat Grandma. |  |
| qwen2.5-0.5b+guard@rules | Let's eat Grandma. |  |
| qwen3-0.6b | Let's eat grandma. |  |
| qwen3-0.6b+guard | Let's eat grandma. |  |
| qwen3-0.6b@rules | Let's eat grandma. |  |
| qwen3-0.6b+guard@rules | Let's eat grandma. |  |
| rules+ | Lets eat grandma. |  |
| rules+@kroko+rules | Let's eat grandma. |  |
| rules+@kroko | Let's eat grandma. |  |
| rules-seam | Lets eat grandma |  |
| rules-seam@kroko | Let's eat grandma |  |
| t5-base | Let's eat grandma. |  |
| t5-base+guard | Let's eat grandma. |  |
| t5-base@kroko+rules | Let's eat grandma. |  |
| t5-base+guard@kroko+rules | Let's eat grandma. |  |
| t5-base@rules | Lets eat grandma. |  |
| t5-base+guard@rules | Lets eat grandma. |  |
| t5-mini | Let's eat grandma. |  |
| t5-mini+guard | Let's eat grandma. |  |
| t5-mini@rules#t2 | Let's eat grandma. |  |
| t5-mini+guard@rules#t2 | Let's eat grandma. |  |
| t5-mini@rules | Let's eat grandma. |  |
| t5-mini+guard@rules | Let's eat grandma. |  |
| t5-small-gec | Let's eat grandma |  |
| t5-small-gec+guard | Let's eat grandma. |  |
| t5-small-gec@kroko+rules | Let's eat grandma |  |
| t5-small-gec+guard@kroko+rules | Let's eat grandma. |  |
| t5-small-gec@rules#t2 | Let's eat grandma |  |
| t5-small-gec+guard@rules#t2 | Let's eat grandma. |  |
| t5-small-gec@rules | Let's eat grandma |  |
| t5-small-gec+guard@rules | Let's eat grandma. |  |
| t5-small-synth | Those are great! | MEANING +great, -eat, -grandma, lost 'eat', lost 'grandma' |
| t5-small-synth+guard | Lets eat grandma. |  |
| t5-small-synth@rules | Lets eat burgers. | MEANING +burgers, -grandma, lost 'grandma' |
| t5-small-synth+guard@rules | Lets eat grandma. |  |
| t5-tiny+guard>punct-en+guard@rules | Let's eat grandma. |  |
| t5-tiny | Let's eat grandma. |  |
| t5-tiny+guard | Let's eat grandma. |  |
| t5-tiny@kroko+rules | Let's eat grandma. |  |
| t5-tiny+guard@kroko+rules | Let's eat grandma. |  |
| t5-tiny@rules#t2 | Let's eat grandma. |  |
| t5-tiny+guard@rules#t2 | Let's eat grandma. |  |
| t5-tiny@rules | Let's eat grandma. |  |
| t5-tiny+guard@rules | Let's eat grandma. |  |
