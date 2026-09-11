# GNSS/PNT Source Quarantine and Future Partner Register

**Status:** blocked from production integration  
**Date:** 2026-08-13  
**Purpose:** keep non-commercial, ambiguous, conditional, paid, or partner-only sources out of the implementation-ready [ATLAS x GAIA GNSS/PNT specification](./05-atlas-gaia-gnss-pnt-integrity.md).

## 1. Quarantine rule

A public endpoint, free API key, GitHub adapter, map, downloadable file, or lack of authentication is **not** a commercial-use license.

No source in this document may be called by GAIA or ATLAS production code, used as a silent fallback, included in a paid artifact, or shown as LIVE. It may move to the approved specification only after one of these exists:

- an explicit license allowing commercial use, derivative computation, public display, caching, and the intended level of redistribution; or
- a signed commercial/partner agreement covering those rights; or
- authoritative source-specific evidence that the exact dataset is public domain/CC0/CC BY/ODbL or equivalent.

No partnership outreach is part of the current implementation. This document is a future work register only.

## 2. Azimuth adapter audit

The reviewed Azimuth source adapters must be split instead of copied wholesale.

| Azimuth adapter/source | Status | Reason and required action |
|---|---|---|
| `adsb-aircraft` → Airplanes.live fallback | **Blocked — non-commercial** | The [API guide](https://airplanes.live/api-guide/) labels free access non-commercial. Remove from fallback chain. |
| `adsb-aircraft` → adsb.fi fallback | **Blocked — non-commercial** | The [official open-data README](https://github.com/adsbfi/opendata/blob/main/README.md) says personal, non-commercial use only. Remove from fallback chain. |
| `opensky-aircraft` | **Blocked — commercial license needed** | [OpenSky API docs](https://openskynetwork.github.io/opensky-api/index.html) limit the live public API to research/non-commercial use and require commercial users to contact OpenSky. |
| `gpsjam` | **Hold — no sufficiently explicit commercial license found** | Public CSV access from [GPSJam](https://gpsjam.org/) is not enough. Do not ingest or reproduce GPSJam cells until the exact dataset and derivatives are licensed for commercial use. Rebuild an AIMarket-owned degradation surface from approved sources instead. |
| `stanford-rfi` | **Blocked — CC BY-NC 4.0** | [Stanford GNSS RFI resources](https://rfi.stanford.edu/resources) explicitly restrict the data to non-commercial use. Do not use in a paid portal/capability. |
| `ais-stream` | **Hold — license unclear** | [AISStream documentation](https://aisstream.io/documentation.html) explains access and backend use but does not provide sufficiently explicit commercial redistribution/derivative terms. |
| `dma-ais` | **Hold — dataset license not pinned** | A reachable CSV listing at `web.ais.dk` does not by itself prove commercial reuse/redistribution rights. Require an authoritative license for the exact AIS dataset. |
| `airport-metar` / `notams-faa` | **Misnamed and out of scope** | The adapter reads airport metadata from AviationWeather; it is not a NOTAM or GPS-interference feed. Do not use it as GNSS evidence. |
| `gfw` | **Blocked — non-commercial** | [Global Fishing Watch](https://globalfishingwatch.org/user-guide/) public site/services use non-commercial licensing unless a separate permission path applies. |

## 3. GNSS station and integrity networks on hold

| Source | Status | Why it is not in the current build | Future unlock |
|---|---|---|---|
| NOAA CORS/NCN | **Hold — mixed station ownership/license not explicit enough** | [NOAA says](https://www.ngs.noaa.gov/CORS/index.shtml) station data are distributed free of charge, but the network combines federal, academic, private, and other independently owned stations. “Free distribution” is not a uniform explicit commercial derivative/resale license for every record. | Obtain a source-level license map or restrict to station records explicitly marked CC0/public domain. |
| [IGS Real-Time Service](https://www.igs.org/rts/products/) | **Hold — commercial operational terms need confirmation** | IGS describes open real-time data/products and commercial applications, but current integration guidance and per-stream contributor rights need a source-specific commercial-use decision. | Pin exact caster/products and a current license statement that covers paid derived outputs and redistribution. |
| EarthScope `SEAT_REQUIRED` real-time streams | **Blocked from free build — commercial use is paid** | [EarthScope](https://www.earthscope.org/data/gnss-realtime/) charges per connection for these commercial real-time streams. The free non-commercial license prohibits selling/distributing derived products for downstream fees. | Keep paid RTCM/position streams disabled. The separately documented `UNLIMITED` mountpoints are allowed only under an active zero-seat commercial license. |
| [EGNOS EDAS](https://egnos.gsc-europa.eu/sites/default/files/documents/egnos_edas_sdd_in_force.pdf) | **Conditional access/redistribution** | Service is free and supports professional/commercial applications, but eligibility, registration, territory, and redistribution rules are conditional. It is not a frictionless global open-data source. | Legal/operational review for the AIMarket entity and exact redistribution model. |
| [GeoVeil / ROMPOS interference API](https://geoveil.ro.miluta.ro/apidocs.html) | **Hold — public API, no explicit commercial license found** | The API is technically valuable and exposes Romanian CORS/interference analytics, but public documentation alone does not grant commercial reuse/redistribution rights. | Written commercial-use license or partner agreement. |

## 4. Aviation sources on hold or blocked

| Source | Status | Restriction |
|---|---|---|
| Airplanes.live | **Blocked for free commercial build** | Free API is non-commercial; business access is a separate product. |
| adsb.fi | **Blocked** | Personal, non-commercial only; selling/licensing/renting/leasing data is forbidden. |
| OpenSky Network | **Blocked until commercial license** | Public live API is research/non-commercial; private/commercial entities need a license. |
| ADS-B Exchange Community API | **Blocked until Enterprise** | [Community API](https://www.adsbexchange.com/data-products/) is personal/non-commercial; commercial integration is an Enterprise product. |
| [Wingbits](https://wingbits.com/terms-and-conditions/b2b) | **Blocked/partner-only** | B2B terms do not provide the raw resale/redistribution freedom required for this product. |
| [GPSwise](https://gpswise.aero/map) and similar commercial GNSS maps | **Partner candidate only** | No open commercial API/data license suitable for republishing was verified. |

Production code must not contain an ordered list that silently falls through among these providers. Every response must identify the actual provider used.

## 5. Maritime sources on hold or blocked

| Source | Status | Restriction |
|---|---|---|
| AISStream.io | **Hold** | Free technical access exists, but sufficiently explicit commercial data licensing/redistribution terms were not found. |
| Danish Maritime Authority AIS dump (`web.ais.dk`) | **Hold** | Direct download exists; exact commercial license and redistribution terms were not pinned. |
| [USCG NAIS](https://www.navcen.uscg.gov/ais-data-sharing-categories-requirements) | **Blocked for this resale model** | USCG data-sharing categories can prohibit retransmission/commercial use depending on access category. |
| [Global Fishing Watch](https://globalfishingwatch.org/user-guide/) | **Blocked — non-commercial** | Public platform/service licensing is non-commercial absent separate permission. |
| Commercial satellite AIS providers | **Partner/paid candidates** | Spire, ORBCOMM, Kpler/MarineTraffic, and similar services require commercial contracts. |

## 6. Government event/advisory sources on hold

| Source | Status | Restriction |
|---|---|---|
| [FAA NOTAM Management System API](https://www.faa.gov/about/initiatives/notam) | **Hold — access approval/API terms** | FAA NOTAM information is public, but the production API access path requires registration/approval and exact automated redistribution terms must be pinned. |
| [FAA planned GPS interference testing page](https://www.fly.faa.gov/ois/dod/gps_dod_sys) | **Hold — no supported product API** | The public page is useful operational context, but scraping a presentation page is brittle and not an implementation-grade licensed API contract. |
| [GPS.gov/NAVCEN anomaly reports](https://www.gps.gov/gps-service-outage-status-reports) | **Hold — source-specific automation license/API missing** | Public government information is valuable, but exact structured feed and reuse metadata should be established before paid redistribution. |
| [EUROCONTROL AUGUR](https://augur.eurocontrol.int/status/) | **Hold — use/access terms not verified** | GNSS advisories and interference views are relevant, but no verified open commercial API/data license was established for this build. |

## 7. Research-only methods and datasets

Research papers may inform AIMarket-owned algorithms when their publication terms allow reading/citation, but their hosted data do not become commercially reusable merely because the paper is public.

| Item | Allowed now | Not allowed now |
|---|---|---|
| Stanford ADS-B GNSS interference method | Reimplement general published ideas from first principles and cite the paper where appropriate | Copy, ingest, cache, or resell Stanford’s CC BY-NC data |
| GPSJam visualization/method ideas | Learn from the public presentation and build an independently derived surface from approved raw sources | Copy GPSJam tiles/CSV or imply GPSJam endorsement without a commercial data license |
| CYGNSS RFI research papers | Use the scientific method to process approved NASA CC0 mission data and cite the research | Treat a research author’s derived dataset/code as commercially licensed without checking its own license |

## 8. Promotion checklist

To move a source from quarantine into production, create a pull request containing all of:

1. exact dataset/API name and endpoint;
2. publisher/rightsholder identity;
3. immutable or archived license/terms URL and retrieval date;
4. explicit evidence for commercial use;
5. explicit evidence for public display, caching, derivative computation, and the intended redistribution;
6. attribution text and modification notice;
7. rate limits, authentication, SLA/no-SLA, and acceptable polling pattern;
8. privacy/security review;
9. source-specific adapter tests and failure behavior;
10. removal of any contradictory old source classification.

Until that checklist passes, the source stays disabled—even if it returns excellent data in a browser or a local curl.

## 9. First-party and contributor sensors

Future AIMarket-operated RF/GNSS receivers can be added without an external data license once ownership and commercial rights are documented. Third-party contributor devices remain quarantined until their onboarding agreement explicitly permits paid derivative products, public map display, caching, and source-attributed redistribution. A configured but offline Edge IoT placeholder is not a source and must contribute neither a point nor a count.
