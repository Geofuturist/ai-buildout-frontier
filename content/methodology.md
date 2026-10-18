# Methodology

**Datasets:** abf-layers, United States, version {version_layers} (DOI: {DOI_layers}) ·
abf-boundaries, version {version_boundaries} (DOI: {DOI_boundaries}) · abf-fra, France, version {version:abf-fra} (DOI: {DOI:abf-fra}). Each dataset has its own DOI and is cited on its own.

## What this site is

AI Buildout Frontier is an open observatory of data layers on the physical side of AI. It covers the
power system of the United States by county: what generates electricity, how much is consumed,
where transmission lines run, and what is waiting to connect to the grid. For France it covers
generation, consumption and transmission lines by department, and the data centers that can be
found in the national register of classified installations. Further countries and layers follow.

The project started from a research question: which of the indicators that AI governance relies
on can actually be collected from open data and checked by someone else? The map is how we work
on that question. Every layer on it can be downloaded, cited and rebuilt from its source.

## How to read a layer

**A layer is named after its source, not after what it might stand for.** “Generation · EIA-860 ·
county” tells you what EIA-860 lists for a county. It does not tell you how much power that county
can supply. We keep the two apart because a layer states a fact. An estimate would need its own
assumptions, and those belong in a methods text, not in the data.

**Blank is not zero.** We separate three states: there is a value; we looked and found nothing; we
have not looked. A county with 0 MW of generation is a statement that EIA-860 lists no operating
generator there. A county marked “Not covered” in the legend is not covered by the layer. Sometimes
a covered county has an empty field because the value does not exist, for example the highest
voltage in a county with no line. The pop-up then says why.

**Each layer keeps its source's license.** The project has no single data license. Our own code is
under the MIT license, and our own compilations, such as the boundary set, are under CC BY 4.0. If
you combine layers, join them by unit code (`unit_id` or `fips`). The combined file carries the
obligations of every license in it.

**Every layer shows its dates**: the period the source covers and the day we built the layer. The
map shows them too, because the sources update on different schedules, from yearly to never again.

**Every layer states how it was checked.** All energy layers are published as the source gives
them (`source_as_is`). Our scripts place, sum or measure the source's own records and run the
automated checks listed below. No value in them was re-checked by a person or by an AI agent. A
layer that rests on judgment, such as deciding which registry entry is a data center, states how
much of that judgment was re-checked and by whom: in the French data-center layer, every record was
re-checked by an independent AI agent.

## United States · abf-layers

| Layer | Source | Value per county | Data through | License |
|---|---|---|---|---|
| Generation | Form EIA-860, U.S. Energy Information Administration | net summer capacity of operating generators, MW; number of generators; number of plants | {current_through:energy_generation_eia860_adm2} | U.S. Government work |
| Demand | OEDI submission 8562, National Laboratory of the Rockies | highest hourly electricity demand in the year, MW (modeled) | {current_through:energy_demand_nrel8562_adm2} | CC BY 4.0 |
| Transmission lines | HIFLD national transmission-line file, archived copy | km of line inside the county by voltage class; highest voltage present. The line segments are a separate layer | {current_through:energy_transmission_hifld_adm2} | Public domain (publisher statement in HIFLD metadata; produced by ORNL for DOE) |
| Interconnection queue | Queued Up, Lawrence Berkeley National Laboratory and GridTracker | MW and number of active requests to connect to the grid | {current_through:energy_queue_lbnl_adm2} | CC BY 4.0 |

Every county layer lists all 3,144 counties and county-equivalents of the United States. Values
cover 3,109 of them: the 48 contiguous states and the District of Columbia. Alaska and Hawaii are
listed but marked not covered, because they need their own map projection. In the queue layer the
nine Connecticut planning regions are not covered either (see below).

### Generation · EIA-860 · county

- **Edition.** Form EIA-860, {edition:energy_generation_eia860_adm2} · data through
  {current_through:energy_generation_eia860_adm2}. EIA publishes a new edition every year.
- **What is counted.** Only generators with status “OP”, operating. Generators on standby or
  temporarily out of service are left out. The value is net summer capacity as reported to EIA. We
  count both generators and plants, because one plant often has many generators.
- **How plants are placed in counties.** By their coordinates: first a plain point-in-polygon test.
  A few plants on the shore fall just outside every county, because the Census cartographic
  boundaries are trimmed to the coastline. For those we take the nearest county within 1 km. When
  we first built the layer, on the 2024 edition, we checked this rule against EIA's own county
  field for the 8 plants it affected, and all 8 matched. Three offshore wind plants, Block Island,
  South Fork Wind and the Coastal Virginia Offshore Wind pilot, lie farther out. Together they have
  171.3 MW and are not assigned to any county.
- **What it does not show.** Form EIA-860 covers power plants with a combined nameplate capacity of
  1 MW or more. Emergency and standby generators at data centers and other buildings are generally
  not reported to it. Generators that entered service after
  {current_through:energy_generation_eia860_adm2} are not in this edition.

### Demand · NREL OEDI 8562 · county

- **Edition.** OEDI submission 8562, {edition:energy_demand_nrel8562_adm2} · data through
  {current_through:energy_demand_nrel8562_adm2}. The dataset is static: a later year would need a
  new submission.
- **What the value is.** For each county, the highest hourly electricity demand in 2023, in MW.
  2023 is the last year of the dataset's 2016–2023 series.
- **How the dataset is modeled.** Utilities do not meter or publish demand by county, so the
  dataset estimates it. Retail electricity sales reported by utilities are totaled by state and
  allocated to counties by each county's share of the state population. The hourly shape comes from
  the reported demand of the surrounding balancing-authority regions. Power plants' reported direct
  use and estimated self-consumption of rooftop solar are added separately.
- **What it does not show.** Measured demand at any place. Because sales are spread by population,
  a large load that does not follow population, such as a data center campus in a county with few
  residents, is spread across its state rather than placed in its county.
- **Attribution.** Kodi Obika, Wesley Cole and Marie Rivers, National Laboratory of the Rockies
  (NLR), DOI 10.25984/3366592. The laboratory was called the National Renewable Energy Laboratory
  (NREL) until December 2025; the layer keeps the name NREL, under which the dataset was announced.

### Transmission lines · HIFLD · county

- **Edition.** {edition:energy_transmission_hifld_adm2} · data through
  {current_through:energy_transmission_hifld_adm2}. The source is no longer updated.
- **What the values are.** Kilometers of line inside the county by voltage class, their total, the
  highest voltage present, whether the county has any line at all, and what share of its line
  length has no recorded voltage. The classes are 69, 115, 138, 230, 345 and 500 kV, 735 kV and
  above, and one class for lines below 69 kV or without a recorded voltage.
- **Inside, not across.** We measure line length inside each county. We do not count lines crossing
  a county boundary, because a boundary shifted by a kilometer can flip that count while the length
  inside barely changes. The kilometer columns are rounded to whole kilometers, so their total can
  differ from the true length by up to 4 km.
- **Empty values.** Twelve county-equivalents have no HIFLD line inside them: four independent
  cities in Virginia, the islands of Nantucket and Martha's Vineyard, and six rural counties. In
  two more, Hamilton County, Iowa, and Clare County, Michigan, the line inside is shorter than
  0.5 km, so the total rounds to 0 km while “has any line” says yes. Where a county has lines but
  none with a recorded voltage, the highest voltage is left blank.
- **Where the data comes from.** HIFLD Open, the public portal that distributed this file, was
  discontinued by the U.S. Department of Homeland Security on 26 August 2025; the announcement gave
  no reason. We use an archived copy of the national file: the copy is dated 26 February 2026, and
  its newest record is from 26 September 2024. Other public archives of the file exist, for example
  on DataLumos (DOI 10.3886/E240591V1). Which archive our copy came from was not recorded, and we
  have not matched it to those archives record by record. So we publish our copy itself next to
  the layer, and anyone can check our processing against it.
- **License.** Public domain (publisher statement in HIFLD metadata; produced by ORNL for DOE). Our
  archive carries no dataset metadata of its own, so the statement is taken from a copy of the
  publisher's metadata for the same edition, kept by the Penn State Data Commons. The lines were
  produced by Oak Ridge National Laboratory, which a contractor runs for the Department of Energy.
  That is why we rely on the publisher's statement and not on the rule for works of federal
  employees.
- **Was the geometry withdrawn?** Before we publish the location of infrastructure, we check
  whether its publisher withdrew it for security reasons (see “What we do not publish”). HIFLD did
  not: no reason was given for closing the portal, and the U.S. Energy Atlas of EIA still offers
  the transmission-line file as an archived layer.
- **What it does not show.** How much power can flow into a county. An earlier version of this
  project estimated that from line ratings, and we dropped the estimate (see “Why there is no
  index”).

### Transmission lines · HIFLD · segments

- **What it is.** The 93,880 line segments of the same archived file inside the contiguous United
  States. Each keeps its HIFLD ID, voltage, voltage class, owner and status (in service or not
  available).
- **Voltage band.** Each segment also gets a band shared by all transmission layers of the project:
  below 100 kV, 100–199, 200–299, 300–399, 400–599, 600 kV and above, direct current, unknown. The
  band is computed from the recorded voltage; the class is used only when no number is recorded. A
  segment without a usable voltage is in the band “unknown”. The direct-current band is empty in
  this release, because no segment in the file is marked as direct current.
- Edition, license and provenance are the same as for the county layer above.

### Interconnection queue · LBNL Queued Up · county

- **Edition.** {edition:energy_queue_lbnl_adm2} data file · data through
  {current_through:energy_queue_lbnl_adm2}. A new edition appears every year.
- **What the value is.** Megawatts and number of projects with an active request to connect to the
  grid, by the county where the project would be built. All grid operator regions are included.
  When a request has more than one capacity value in the file, we take the largest, not the sum.
- **What is left out.** Requests with a capacity of zero or less; requests outside the contiguous
  states or with no state given; requests without a county code; and requests in Connecticut. The
  source codes Connecticut projects by the state's former counties, which do not map onto the
  planning regions the Census has used since 2022. So the nine regions are marked not covered
  rather than shown as zero. The layer's known gaps list each excluded group with its count and
  megawatts. Together, the groups account exactly for the difference between the layer and the
  source file.
- **What it does not show.** These are power plants and batteries asking to connect, not
  electricity users. Most requests are never built. There is no public county-level queue of new
  large loads such as data centers: utilities and grid operators collect that information, but in
  the cases we checked they keep it confidential.
- **Attribution.** “Lawrence Berkeley National Laboratory and GridTracker”, as the license asks.
  This is the jointly released data file under CC BY 4.0. It is not the GridTracker website, whose
  terms do not allow reuse.

## France · abf-fra

The French layers form a separate dataset, abf-fra, with its own DOI. They cover the 101
departments: the 96 of metropolitan France, Corsica included, and the five overseas departments.
Values are attached to a department by the department code given in each source, not by
geometry. The exception is transmission lines, whose length is measured inside each department.
Department outlines come from Natural Earth 1:10m (see "Administrative boundaries"), so they are
generalized. Department names follow the official geographic code of INSEE: where Natural Earth
spells a name differently, the INSEE spelling is used.

From version 0.2.0, the three energy layers are also published for the 18 regions. Their sections
follow the data-center layer below.

| Layer | Source | Value per department | Data as of | License |
|---|---|---|---|---|
| Generation | National register of production and storage installations, via ODRÉ | maximum installed capacity of operating installations, MW, by technology group; storage separately | 31 July 2026 | Licence Ouverte / Open Licence 2.0 |
| Electricity consumption | Agence ORE | electricity delivered in the year, MWh, by sector; number of delivery points | year 2024 | Licence Ouverte / Open Licence 1.0 (departments), 2.0 (regions) |
| Transmission lines | RTE line data, in a copy republished by DDTM de l'Eure | km of line in operation inside the department by voltage band | 30 June 2023 | Licence Ouverte / Open Licence 2.0 |
| Data centers | Register of classified installations (ICPE), Géorisques | points: data centers present in the register | extract of 10 October 2026 | Licence Ouverte / Open Licence 2.0 |

French and U.S. values measure different things: maximum installed capacity rather than net summer
capacity, delivered energy over a year rather than a modeled peak hour. Compare them only with that
in mind.

### Generation · ODRÉ national register · department

- **Edition.** Registre national des installations de production et de stockage d'électricité,
  snapshot of 31 July 2026, published on Open Data Réseaux Énergies (ODRÉ) and updated monthly. RTE
  compiles the register from its own data and the data of the distribution network operators:
  Enedis, EDF SEI and local distribution companies.
- **What is counted.** The maximum installed capacity (puissance maximale installée) of the
  installations in operation on the snapshot date. An installation counts unless it has a
  disconnection date, was commissioned after the snapshot date, or is marked as temporarily
  withdrawn. Installations without a commissioning date are counted, because the register lists
  them. Installations under 36 kW are aggregated in the register and included.
- **Groups and storage.** Technology groups follow the register: nuclear, fossil (non-renewable
  thermal), hydro, wind, solar, bioenergy and other. Pumped-storage hydro stays in hydro, as the
  register classifies it. Other storage, mostly batteries, is a separate column and is not part of
  the total.
- **What is left out.** Aggregated rows without a department code (34.1 MW), and installations in
  Saint-Pierre-et-Miquelon, Saint-Barthélemy and Saint-Martin (135.1 MW), which are not
  departments. With them, the department values add up exactly to the register total.
- **Closed plants.** If a plant on our list of known closures appears as operating, the build stops
  and the case is decided from public sources. The list and every decision are in the code
  repository.

### Electricity consumption · Agence ORE · department

- **Edition.** "Consommation annuelle d'électricité et gaz par département", Agence ORE, year 2024.
  Only electricity is used.
- **What the value is.** Electricity delivered to consumers in the department during the year, in
  MWh, as reported by the grid operators: in total and by sector (residential, tertiary, industry,
  agriculture, unknown), with the number of delivery points. Consumers connected directly to the
  transmission network are included.
- **Not peak power.** This is metered energy over a year. It is not comparable with the modeled peak
  hour of the U.S. demand layer.
- **Rows without a value.** In 31 departments the source publishes 85 department × sector rows
  without a value. Totals there are lower bounds; the field `n_rows_without_value` marks them.
- **Confidentiality.** The source hides small values at municipal level. We compared the department
  file with the sum of the municipal file of the same source: department totals are 0.12% higher
  nationally, so they are not reduced by this confidentiality.

### Transmission lines · RTE · department

- **Edition.** RTE's datasets of overhead and underground lines, data as of 30 June 2023, in the
  copy republished by the Direction départementale des territoires et de la mer de l'Eure on
  data.gouv.fr.
- **Why a 2023 copy, and why no segments.** RTE's current list of lines on ODRÉ (edition of 16 June
  2026) has no coordinates. Its description says: "RTE a fait évoluer l'accès aux données GPS des
  infrastructures du réseau public de transport pour des raisons de sécurité publique" (RTE has
  changed access to the GPS data of the transmission network for reasons of public security;
  https://odre.opendatasoft.com/explore/dataset/lignes-aeriennes-rte-nv/). We do not republish locations that their operator withdrew for security (see "What we
  do not publish"), even when an older copy and its license would allow it. So the line segments
  are not published. Kilometers per department are: they do not show where a line runs.
- **What the values are.** The same method as the U.S. county layer: length of line inside the
  department, by the voltage bands shared by all transmission layers of the project. Direct-current
  lines have their own column. Lines recorded as de-energized (hors tension) are counted without a
  voltage. Only lines in operation are counted; lines with an administrative approval that are not
  yet built are left out.
- **Coverage.** 94 departments of continental France. Corsica and the overseas departments have
  grids separate from the RTE network and are marked not covered.
- **Outlines.** Department outlines are Natural Earth 1:10m, so a line within about a kilometer of
  a department boundary may be counted in the neighboring department. 793.5 km of line lie outside
  the 94 departments (coast and international connections) and are not counted.
- **What it does not show.** How much power can flow into a department.

### Data centers · classified installations (ICPE), Géorisques · points

- **The register.** France registers installations whose activities exceed environmental
  thresholds as installations classified for environmental protection (ICPE). Géorisques publishes
  the register. A data center appears in it when its installations cross these thresholds. Being
  in the register is a fact about the register: it says nothing about the size of the site, and
  data centers below the thresholds are not in it at all.
- **Finding data centers in it.** The register has no category for data centers, and its activity
  codes are two-digit divisions only. We select records by three rules: the name contains a
  data-center term; the operator is on our list of data-center operators (for operators with other
  lines of business, only when the name also points to a data center); or the site is named as a
  data center in a public document of its operator. The rules and lists are in the code
  repository. Each point records which rule found it.
- **Checking.** An independent AI agent, working from a written protocol and not involved in
  writing the rules, checked each selected record against its register card and a public source.
  The agent can confirm or dispute a record; it cannot add one. Of 46 selected records, 43 were
  confirmed and are published; 3 could not be confirmed and are left out. The agent's verdicts are
  published with the dataset (icpe_agent_verdicts.csv).
- **Misses.** The agent also checked random samples of records the rules left out. They contained
  data centers, and the rules were extended to include them. From the last sample we estimate that
  roughly 3 to 72 of the 177 left-out records that were never checked may be data centers. The
  layer is therefore a lower bound of the data centers in the register.
- **Location.** The register gives coordinates but not their precision, so every point is shown at
  commune precision. We do not use geocoders.
- **What is not published.** Classification headings (rubriques), the regime of the installation,
  its equipment and the contents of inspections are never collected into the layer.

### Generation · ODRÉ national register · region

The same register, snapshot and rules as the department layer. The difference is how an
installation is placed: by the region code in the register, not by summing departments. Some
aggregated rows of small installations have a region code but no department code (36 rows,
28.9 MW). They are in a region but in no department, so a region total can be larger than the sum of
its departments. Thirteen such rows have no region code either (5.2 MW) and are left out, as are
Saint-Pierre-et-Miquelon, Saint-Barthélemy and Saint-Martin.

### Electricity consumption · Agence ORE · region

Taken from Agence ORE's dataset by region for 2024, not summed from departments. Following our rule
of using a source at its own resolution, we prefer the source's own regional figures. The datasets
by region and by department are separate extracts: nationally the regions are 0.10% higher than the
sum of the departments, and no region differs by more than 1%. The source does not explain the
difference. Unlike the department dataset, the regional one has no rows without a value. Everything
else is as in the department layer: delivered energy over a year, not peak power.

### Transmission lines · RTE · region

The same line data, method and rules as the department layer. Regions are merged from the same
department outlines, so region totals equal the sums of their departments. Corsica and the five
overseas regions are not covered.

## Administrative boundaries · ADM0, ADM1, ADM2

- **One frame for the whole world.** Natural Earth at 1:10 million, version 5.1.2. Where borders
  are disputed, we use the U.S. government's point of view, because the main sources in this
  project are U.S. federal. **The boundaries do not express a position of the project.** Five
  disputed areas belong to no country in this view: Abyei, the Ilemi Triangle, the Siachen Glacier,
  the Southern Patagonian Ice Field and Rincón de Artigas. They are drawn with a neutral fill, not
  left blank like the sea.
- **Who controls an area is recorded as a fact, not drawn as a border.** Where the state in control
  differs from the state shown, the area is listed in the layer contested_areas, with both states,
  the date and sources; the frame stays as it is. This release lists two areas: Crimea and
  Sevastopol. The layer is made of whole units of the frame, so areas where control covers only
  part of a unit, such as areas of eastern and southern Ukraine since 2022, are not listed.
- **Levels follow each country's own structure**, not whatever a source calls “admin-1”. This
  release:

  | Country | First level | Second level | Source |
  |---|---|---|---|
  | World | 242 countries and territories | — | Natural Earth |
  | United States | 51 (states and the District of Columbia) | 3,144 counties and county-equivalents | U.S. Census Bureau cartographic boundaries 1:500,000, 2023 |
  | France | 18 regions | 101 departments | Natural Earth, merged |
  | United Kingdom | 4 countries | — | Natural Earth, merged |
  | Norway | 15 counties and Svalbard | 357 municipalities | Kartverket, CC BY 4.0, reference date 1 January 2026 |
  | 104 more countries | 1,578 units: the top level of ISO 3166-2 | — | Natural Earth, as is or merged; codes and names from Unicode CLDR |

- **The first level of the 104 countries** is the top level of ISO 3166-2, the international
  standard for subdivision codes, as recorded in Unicode CLDR release-48-2. Natural Earth units are
  taken as they are or merged, and only where they match that list code for code. A few written
  corrections apply: subtypes of one level count as one level, such as states and a federal
  district; codes of territories that our frame shows as separate countries are left out; where the
  top level is not administrative, the next one is used, case by case with an official document
  (Guinea-Bissau in this release); small parts of a country that have no code in the list stay in
  the country without a first-level unit, up to 1% of its area; a country where five or more units
  lie inside other units, such as cities inside counties, is held back for review. Names are the
  English names of the codes in CLDR.
- **How the first level was checked.** For every country, a script matched the units to the CLDR
  code list. A random sample of countries, and every country whose units were merged, matched by
  name or left with parts outside any unit, was checked against official national lists by an
  independent AI agent. The verification sample covers countries whose official lists could be
  retrieved. Each country's entry in the boundary registry
  (https://github.com/Geofuturist/ai-buildout-frontier/blob/main/boundaries/boundary_registry.csv)
  records its method, its expected number of units and what it was checked against.
- **What may be out of date.** ADM1 follows the top level of ISO 3166-2 as recorded in Unicode CLDR
  release-48-2; reforms after that release may not be reflected. The other 134 countries and
  territories show national borders only, until we check their subdivisions against an official
  list. Burkina Faso and Vietnam are among them: both reorganized their first level in 2025, and the
  reference does not reflect it. An outdated division on a site about checkable data would be worse
  than none.
- **Fitting national data to the frame.** National boundaries of the United States and Norway are
  fitted to the frame along land borders with neighbors only. The coastline stays national.
- **Two geometries.** Calculations use the official boundaries at full resolution: for the United
  States, the Census 1:500,000 files. The map shows a simplified version. Both carry the same unit
  codes, so what you see is what we counted on. The subdivisions of all other countries come from
  Natural Earth and are generalized: they are not the official national boundaries.
- **Cut to the country.** First-level units are cut to the outline of their country. Where Natural
  Earth draws a unit beyond that outline, the part outside is left out and listed in the validation
  report; the largest is 2,268 km² of Ladakh (IND-1-LA) inside the outline of China in this point of
  view.
- **Unit codes.** Countries: ISO 3166 three-letter codes (`USA`). Subdivisions:
  `{country}-{level}-{national code}`, for example `USA-1-51` (Virginia) or `USA-2-51059` (Fairfax
  County). For the 104 countries added in version 0.2.0, the national code is the ISO 3166-2 code:
  `POL-1-24` is Silesia. France keeps its INSEE codes (`FRA-1-84`).
- **Checks run at every build.** No overlaps between units. No gaps except a reviewed list of seas,
  disputed areas and slivers. No land outside every country: the country layer is compared with the
  land of the Natural Earth admin-1 file, and an uncovered area of 100 km² or more stops the build.
  We added this check after version 0.1.0 left Adjara, part of Georgia, outside every country;
  version 0.2.0 corrects it. Every unit inside its parent. Unit counts as expected. Subdivisions
  are published only for countries whose entry in the boundary registry has been verified. The build was reproduced on a second machine.
- **License.** CC BY 4.0 for the boundary set. Each unit carries its own source and license. Codes
  and English names of the first level come from Unicode CLDR (© Unicode, Inc., Unicode License v3).

## Counties, county-equivalents and cities

“County” on this site means a county or county-equivalent as the Census defines it. In Virginia that
is 133 county-equivalents (95 counties + 38 independent cities). Independent cities are separate
units: St. Louis city and St. Louis County in Missouri are two rows, not one. Connecticut appears as
9 planning regions, as in the 2023 Census files, not as its 8 former counties. Areas are computed in
equal-area projections.

## Downloading and citing

- **Formats.** Every layer comes as GeoParquet (the main format, readable by GeoPandas and DuckDB),
  gzipped GeoJSON and CSV without geometry. Map tiles are for display only.
- **Joining.** Join on `unit_id`, or in U.S. layers on the five-digit `fips` code. Read codes as
  text, or leading zeros disappear.
- **Stable links.** Files sit at fixed, versioned addresses. A new version gets a new address, and
  old ones keep working. The current version is listed in `manifest/latest.json` with file sizes
  and checksums.
- **Citing.** Cite the layer, the version and the DOI of its dataset: {DOI_layers} for the U.S.
  energy layers, {DOI:abf-fra} for France,
  {DOI_boundaries} for the boundaries. Each layer card gives a ready citation, and each pop-up gives
  one for the single record. Please also credit the original source as its license requires. The
  attribution text of each layer is in its metadata and on the Sources and licenses page.

## What we checked

**On every build, for every layer:**
- every input file is fingerprinted (SHA-256), and the fingerprint is published in the layer's
  metadata;
- if an input is missing or incomplete, the build stops, so a failed download cannot turn into
  zeros;
- field names and types are checked against the layer's declared schema;
- every county layer lists each unit of the frame exactly once, and every unit code exists in
  abf-boundaries;
- the totals in the published files equal the totals of the build.

**Against the source:**
- **Generation.** The capacity of operating generators in the EIA-860 workbook equals the layer
  total plus the three offshore wind plants outside every county.
- **Interconnection queue.** The active requests in the Queued Up workbook equal the requests in the
  layer plus the excluded groups listed in its known gaps, both in number and in megawatts.
- **Transmission lines, county.** The kilometer totals are checked against the “has any line”
  field. The two counties where they disagree because of rounding are listed in the layer's known
  gaps.
- **Transmission lines, county and segments.** A script checks the license statement against the
  copy of the publisher's metadata.
- **Transmission lines, segments.** Every segment ID is unique.

**France:**
- **Generation.** The department values plus the rows left out (no department code; Saint-Pierre-et-
  Miquelon, Saint-Barthélemy, Saint-Martin) equal the capacity of operating installations in the
  register, to the kilowatt.
- **Electricity consumption.** The department values equal the source total for 2024, in every
  column. Department totals were compared with the municipal file of the same source.
- **Transmission lines.** When the layer was built, the department totals were checked against the
  length of all line segments inside the 94 departments.
- **Data centers.** Every published record was re-checked by an independent AI agent; samples of
  the records left out were checked for misses (see the layer section).
- **Regions.** Generation: the region values plus the rows left out equal the register total, and
  each region differs from the sum of its departments exactly by its rows without a department
  code. Transmission lines: region totals equal the sums of the department totals. Consumption: the
  regions add up to the total of the regional file and were compared with the department values.

**Against our earlier Virginia pipeline.** When we first built these layers in September 2026, on
the 2024 edition of EIA-860 and the 2025 edition of Queued Up, we compared them with the pipeline
behind version 1.0 for Virginia's 133 county-equivalents:
- demand matched in all 133;
- the queue differed in 1, explained by including all grid regions instead of one;
- generation differed in 10. These are 5 pairs of neighboring units, together 0.7% of Virginia's
  capacity: plants near a boundary landed on the other side, because the old and new boundary files
  are drawn slightly differently.

**Published files do not change.** Once a version is published, its files are fixed, and every new
publication checks them by checksum. Corrections come as a new version.

## Known limitations

- **Generation** covers generators operating at the end of the edition year. Generators that
  entered service later are missing until the next edition.
- **Demand** is modeled and spread by population, so it may misplace large single loads.
- **Transmission** comes from an archive whose newest record is from September 2024, and the
  source is no longer updated. Some lines have no recorded voltage.
- **The queue** lists requests, not plants that will be built, and generation, not demand.
- **Alaska and Hawaii** are not covered, and in the queue layer neither is Connecticut.
- **France, transmission** comes from a copy with data as of June 2023 and is published only as
  department totals. Corsica and the overseas departments are not covered.
- **France, data centers** is a lower bound: data centers registered under names and operators we
  could not identify are missed, and the points are at commune precision.
- **Boundaries** outside the United States and Norway are generalized at 1:10 million. First levels
  of 104 countries follow CLDR release-48-2 and may miss later reforms; 134 countries and
  territories have national borders only.

## What we do not publish

- **Vulnerability of specific facilities**: how they could be reached or disabled, single points
  of failure, security.
- **How long a specific facility could run without the grid**: fuel, permitted generator hours,
  backup configuration. Such figures appear only as totals for regions or classes, never for fewer
  than three facilities.
- **Locations withdrawn for security.** If the publisher of infrastructure locations withdraws them
  and gives security as the reason, we do not republish older copies. We publish totals by area
  instead. This is why France's transmission lines appear only as department totals.
- **Classification details of installations**: for the French data-center layer, the
  classification headings, regime, equipment and inspection contents from the register.
- **Substations from OpenStreetMap.** We built this layer, but it is not in this release: coverage
  is uneven, and its license (ODbL) would carry over to any file it is merged into.
- **A composite score.** See below.

## Why there is no index

Version 1.0 of this site, in April 2026, published a “grid feasibility index” for Virginia's 133
county-equivalents. While building a national version, we checked the index against its raw inputs
and dropped it.

- **The transmission term was demand under another name.** In 128 of the 133 units it hit a cap set
  at half of adjusted peak demand. In those rows it was exactly 0.5 × demand, so its 0.9995
  correlation with demand was an identity, not a finding.
- **The cap threw away most of the transmission signal.** Across those 128 rows the median import
  estimate fell from 1,281 MW to 41 MW (from 1,230 to 38 MW across all 133), and 94.5% of the total
  by sum.
- **The “severe” band held only artifacts.** Five units sat at −1.0: places with no generation and
  no transmission lines at all. Forty more sat at exactly −0.5, the floor the formula could not go
  below.

An index asks readers to trust its author. Layers ask them to trust EIA, NLR, HIFLD and LBNL, and
then let them check. The version 1.0 methodology is archived at {archive_v1_url}.

## How this was built

One researcher, working with AI coding assistants. The code is public on GitHub
(https://github.com/Geofuturist/ai-buildout-frontier) under the MIT license. AI tools helped write
the code and these texts, but they are not a source: every value comes from a file listed in the
layer's metadata, and the checks above are scripts, not model output.

**Found an error?** Open an issue on GitHub. Corrections are listed with the version that fixes
them.
