# Almanara

### One shared way for government to evaluate, approve and monitor AI.

## 👉 [Check out the live demo](https://almanaramain-frontend.vercel.app)

Today, every department picking an AI model starts from zero: the same tests, the same paperwork, and no clear owner when something goes wrong.

**Almanara fixes that.** Eight AI agents take a use case from idea to approved, monitored model. Evidence is shared across departments, and a named person always makes the final decision.

Built to cut evaluation time by **80%**. In our sample assessment history, it saved **83%**.

## Try it in 1 minute

Open the demo and pick a login. Each one sees something different:

| Log in as | What you can do |
|---|---|
| **Director** | See every department. Approve, pause and re-check models. |
| **Department head** | Do the same, for Traffic & Fines only. |
| **Employee** | Start and follow use cases in Traffic & Fines. View only. |

The first load can take up to a minute while the server wakes up.

## Features

- **Use-Case Card:** describe what the AI will do, or upload a document.
- **Automatic risk rating:** low, medium or high, with the reasons shown.
- **Eight AI agents:** each one handles a step, from compliance to red-team testing.
- **Reuse across departments:** approved models and evidence are shared, so nobody tests from scratch.
- **Arabic and fairness testing:** includes Gulf dialect, accessibility and the right to appeal.
- **Real UAE data:** models are tested on 7 public tables from Bayanat.ae.
- **Human sign-off:** AI recommends, but a named person decides and is accountable.
- **Live monitoring:** models go back for re-checks when something changes.
- **ROI tracking:** see what each model saves and what it costs.
- **Role-based access:** directors, department heads and employees each get their own view.

## How it works

**Use case → Risk rating → Evidence → Testing → Human approval → Monitoring**

## About this demo

- Models are tested on real UAE government data from Bayanat.ae, alongside hand-written test cases.
- Department, staff and model names are placeholders.
- There are no passwords, so anyone can try any role.
- The New use case page is a guided simulation. The other pages can show data from the live backend.

## Built with

FastAPI, PostgreSQL, OpenRouter and plain HTML, CSS and JavaScript. Hosted on Render and Vercel.

Built for TDRA Challenge #11. Technical details and setup are in [HANDOFF.md](HANDOFF.md).
