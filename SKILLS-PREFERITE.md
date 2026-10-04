# Skill e strumenti da usare sempre

Ricostruita il 04/10/2026 da tutte le sessioni Claude Code dei progetti Toto-Amici, Turni_Plus e Wedding S&R.
Da incollare (o citare) a inizio sessione in qualsiasi progetto.

## Regola di lavoro
- **Tutto il lavoro va delegato a sotto-agenti Sonnet.**
- Fare domande su tutto ciò che non si sa, una alla volta, con risposte cliccabili.

## Sempre attive
| Skill | A cosa serve | Dove è installata |
|---|---|---|
| **ponytail** | Codice minimo, niente complessità inutile. Indicatore nella barra di stato | plugin globale (`ponytail@ponytail`) |
| **graphify** | Trasforma il codice in una mappa navigabile delle relazioni fra file. Su Turni_Plus mai senza chiedere, con `graphify-out/` nel `.gitignore` | `~/.claude/skills/graphify` |
| **find-skills** | Trova e installa nel progetto le skill più utili per il lavoro in corso | `~/.claude/skills/find-skills` |

## Front-end e design
| Skill / strumento | A cosa serve |
|---|---|
| **frontend-design** | Direzione estetica, tipografia, scelte non da template |
| **transitions-dev** | Animazioni e transizioni pronte (menu, modali, toast, contatori…) |
| **transitions-polish** | Rifinitura dei tempi e delle curve delle animazioni |
| **agent-skills:frontend-ui-engineering** | Componenti e interfacce di qualità da produzione |
| **design:accessibility-review** | Controllo di accessibilità (WCAG) |
| **design:ux-copy** | Testi dell'interfaccia: pulsanti, errori, messaggi vuoti |
| **dataviz** | Grafici, classifiche, cruscotti leggibili in chiaro e scuro |
| **context7** | Documentazione aggiornata delle librerie (React, Tailwind, Cloudflare…) |
| **21st.dev** (connettore MCP) | Catalogo di componenti UI moderni |
| **OriginKit** (connettore MCP) | Catalogo di componenti UI |
| Aceternity UI, Beautiful UI, Component Gallery | Altre librerie di componenti citate come riferimento |

## Sicurezza e conformità, su tutto ciò che si pubblica
| Skill | A cosa serve |
|---|---|
| **verifica-conformita** | GDPR, privacy, cookie, sicurezza: rapporto in italiano prima di pubblicare |
| **agent-skills:security-and-hardening** | Protezione da vulnerabilità e input malevoli |
| **agent-skills:security-auditor** | Revisione di sicurezza da parte di un agente dedicato |
| **agent-skills:web-performance-auditor** | Velocità e Core Web Vitals |

## Installate solo in Toto-Amici (restyling, 04/10/2026)
Trovate con find-skills, in `.claude/skills/` del progetto:
cloudflare, shadcn, tailwind-design-system, design-motion-principles, vercel-react-best-practices, web-design-guidelines, **apple-design** (Emil Kowalski: principi Apple tradotti per il web) e **playwright-cli** (Microsoft: verifica delle UI dal browser, telefono e computer).

## Da non usare
- **omniroute**: scartato per scelta (28/09/2026), non riproporlo.

## Riferimenti
- Elenco completo per i siti vetrina: `~/Desktop/PROMPT-SITI-VETRINA.md`, sezione "STRUMENTI DA USARE".
