<div align="center">

# Predictive Catenary Monitoring

**From the AutoCAD drafting table to the sensor: structural fatigue monitoring for railway catenary networks.**

A concurrent ingestion gateway in Go receiving telemetry from thousands of
simultaneous sensor points, feeding a Python analysis engine that combines
mechanical vibration with a simplified structural fatigue model to predict
failure points before they happen.

[![Go](https://img.shields.io/badge/Go-00ADD8?logo=go&logoColor=white)](https://go.dev)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![Supabase](https://img.shields.io/badge/Supabase-3FCF8E?logo=supabase&logoColor=white)](https://supabase.com)

`Under development`

[Português](README.md) &nbsp;·&nbsp; **English**

</div>

---

## Why this project

Before I got into programming, I spent 6 months at Systra, a multinational
railway engineering firm, working on infrastructure projects for the São
Paulo Intercity Train (TIC). During that time I produced technical drawings
and control schematics for catenary systems in AutoCAD, the suspended cable
above the track that delivers power to the train through contact with the
pantograph.

Catenary is critical infrastructure under constant mechanical stress:
tension load, vibration from train passage, thermal variation, contact wear.
A failure does not announce itself, it accumulates through fatigue cycles
over months. This project takes the problem I used to see represented as a
floor plan and turns it into the real software engineering problem behind
it: how would a system need to be designed to capture that in real time,
at the scale of thousands of sensor points across an entire line, without
dropping data under load.

This has no ambition of becoming a certified structural engineering
product. The point is to show that I can design the data pipeline a real
railway infrastructure problem would require, from sensor to decision.

---

## The problem, formulated as engineering

> Input: continuous vibration readings from thousands of sensor points along
> the catenary network. Output: a risk classification per point (normal,
> attention, critical), updated in real time, with no ingestion bottleneck
> even under spikes of thousands of messages per second.

Computing fatigue is the easy part. What most academic prototypes ignore is
the systems problem hiding behind it: **ingestion concurrency at scale**. A
single-threaded Python scraper reading sensors one at a time cannot handle
an entire railway line. That is where the language choice stops being
aesthetic and becomes an engineering decision.

---

## Architecture

```
thousands of sensors (simulated)
        │  publish vibration readings
        ▼
┌───────────────────────┐
│   Ingestion Gateway      │  Go, one goroutine per sensor connection,
│         (Go)             │  concurrent aggregation via channels
└───────────┬─────────────┘
            │  aggregated batches
            ▼
┌───────────────────────┐
│    Analysis Engine        │  Python, FFT of the vibration signal,
│      (Python)             │  fatigue accumulation model (simplified
│                           │  Basquin rule), risk classification
└───────────┬─────────────┘
            │  readings + alerts
            ▼
┌───────────────────────┐
│      Supabase              │  Postgres, reading history, alerts,
│    (Postgres)             │  registered sensor points
└───────────┬─────────────┘
            │
            ▼
┌───────────────────────┐
│      Dashboard               │  Streamlit, line map, critical point
│      (Streamlit)            │  ranking, vibration time series
└───────────────────────┘
```

| Layer | Language | Why this choice |
|---|---|---|
| Ingestion gateway | **Go** | Thousands of sensors publishing simultaneously is a concurrency problem, not a compute problem. Goroutines handle thousands of simultaneous connections at a fraction of the memory cost of traditional threads, and channels give a safe way to aggregate readings from multiple goroutines without locks scattered through the code. If this gateway were written in Python, the GIL would become the bottleneck exactly when it matters most, traffic spikes. |
| Analysis engine | **Python** (NumPy, SciPy) | Vibration spectral analysis and the fatigue model are computation, not concurrent I/O. This is where Python's scientific library density pays off, without the overhead of writing linear algebra by hand in Go. |
| Persistence | **Supabase** (Postgres) | Same stack already used in production elsewhere in this portfolio. Reading history becomes one table, alerts another, with a direct relationship between them. |
| Visualization | **Streamlit** | Fast dashboard prototyping without hand-writing a frontend, the same choice made in the other two projects of this portfolio. |

---

## The fatigue model, with an important caveat

Structural damage accumulation here uses a simplified version of the
**Basquin rule** (the relationship between cyclic stress amplitude and
number of cycles to failure), combined with the **Palmgren-Miner rule** to
sum damage from variable-amplitude cycles. It is the same principle used in
real fatigue engineering, but calibrated with example parameters, not with
real catenary cable material test data.

**This does not replace a certified structural analysis.** The final number
the model spits out matters less than the architecture that produces it.
The ingestion, processing and decision pipeline is the same shape a real
monitoring system would use, just with a simplified physical model in
place of proprietary test data.

---

## Current status

| Component | Status |
|---|---|
| Sensor simulator | Planned |
| Ingestion gateway (Go) | Planned |
| Analysis engine (Python) | Planned |
| Persistence (Supabase) | Planned |
| Dashboard (Streamlit) | Planned |

This README documents the architecture before the first line of code, on
purpose: design the pipeline first, so every component has a defined
input/output contract before it exists.

---

## Project structure

```
├── cmd/gateway/       Go ingestion gateway
├── src/                 Python analysis engine
├── scripts/               sensor simulator and utilities
└── docs/
```

---

## Credits

**Course:** Computational Laboratory of Machine Learning (LCML), 2026/2
**Class:** CIB-NA8
**Professor:** Reinaldo Augusto de Oliveira Ramos

Problem domain based on 6 months of professional experience at Systra, on
infrastructure projects for the São Paulo Intercity Train (TIC).
