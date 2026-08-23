# AeroPINN hackathon video script

Target length: **5:50–6:10**  
Recommended spoken pace: **145–155 words per minute**  
Format: one presenter with screen recording; a second person may operate the screen

## Video objective

By the end of the video, a judge should understand:

1. what AeroPINN does and why pantograph contact matters;
2. the exact communication/accessibility task the team received;
3. why post-journey audit is the core human workflow for an autonomous system;
4. which accessibility need is addressed;
5. how automatic logging, text browsing, metadata, and exports implement the solution;
6. how a realistic high-wind scenario demonstrates it; and
7. why this is an improvement to an existing communication feature, not an unrelated
   new feature.

The primary accessibility need to name explicitly is **access to visually encoded live
information for blind or low-vision screen-reader users**. Secondary benefits include
self-paced review for people with cognitive/sensory processing barriers and use on
devices that cannot render the full 3D simulation smoothly.

## Recording plan

Use three prepared views:

- **View A — Browser:** AeroPINN dashboard at `http://localhost:5173`.
- **View B — Task slide:** the exact challenge statement in large text.
- **View C — Files:** an extracted AeroPINN audit ZIP showing its contents.

Record at 1920×1080 if possible. Keep browser zoom at 100%. Use a visible cursor halo,
record narration as captions, and hide bookmarks, notifications, usernames, terminal
history, and unrelated files.

### Pre-recording checklist

Complete this before the first take:

1. Start from the repository root:

   ```bash
   bash run_local.sh
   ```

2. Confirm the backend responds:

   ```bash
   curl http://localhost:8000/health
   ```

3. Open exactly one dashboard tab. Extra tabs create extra independent journeys and
   consume more CPU.
4. Wait until the top-right status reads **LIVE**.
5. Leave the dashboard in **NOMINAL** state: 250 km/h, 100% tension, 1× turbulence.
6. Leave **FORCES ON** and **MOTION ×25** enabled.
7. Open **VALIDATION** once before recording and wait for all background cards to stop
   saying `WARMING UP`. Close it afterward.
8. Open **JOURNEY LOGS** once and confirm the completed
   **High-wind contact stress test** sample exists. Close it afterward.
9. Download one audit package before recording, extract it into a clean folder named
   `AeroPINN-Audit`, and arrange the folder in list view. This is the backup for the
   export shot.
10. Prepare a full-screen task slide containing only:

    > Improve the part of your existing MVP most related to communication so that it
    > can make a core workflow usable for people with at least one accessibility need.
    > The team should be able to demonstrate it using realistic sample data or
    > plausible scenarios.

11. Test the **STRESS TEST** and **GUST** buttons in a rehearsal, then return to
    **NOMINAL** before the recorded take.
12. Keep this script on a second device or printed page so it never appears in the
    recording.

### Editing rules

- Show captions for every spoken line.
- When a metric is mentioned, zoom or highlight it instead of moving the cursor in
  circles.
- Use hard cuts between the dashboard, task slide, and files. Avoid decorative
  transitions.
- Never leave the viewer watching a loading state. Use the prepared completed sample
  or a clean cut if a live request is slow.
- Do not claim railway certification or train/route-specific validation. Use
  “research simulation,” “reference check,” and “plausible scenario.”
- Do not read every number. Explain what a number proves.

## Timeline summary

| Time | Segment | Main visual |
|---|---|---|
| 0:00–0:25 | Hook | Live 3D pantographs and force trace |
| 0:25–0:58 | What AeroPINN is | Dashboard, then validation panel |
| 0:58–1:28 | Assigned task | Full-screen task slide |
| 1:28–2:08 | Accessibility interpretation | Task slide, then dashboard |
| 2:08–2:55 | Plausible live scenario | Stress Test and Gust |
| 2:55–3:40 | Automatic journey audit | Journey catalogue and summary |
| 3:40–4:38 | Detailed text records | Events, physics, constants, raw record |
| 4:38–5:20 | Export and documentation | Export buttons, ZIP contents, metadata |
| 5:20–5:50 | Why this solution fits best | Audit files and dashboard split-screen |
| 5:50–6:05 | Closing | Dashboard hero shot |

## Detailed shooting script

### 0:00–0:25 — Hook: show the problem before naming it

**Screen setup**

- Start on View A with the full dashboard visible.
- Keep the pointer still for the first two seconds.
- Slowly orbit the train just enough to show both pantographs and the contact wire.
- End the orbit with the live force trace and lane cards unobstructed.

**Speaker**

> At high speed, a train’s pantograph must maintain stable contact with the overhead
> wire. Too little force causes separation and arcing; too much force increases wear.
> AeroPINN is our research simulation of an active pantograph that predicts this
> interaction and responds before contact becomes unstable.

**On-screen overlay**

`AeroPINN · active pantograph stabilization · PINN-MPC`

**Presenter note**

Do not explain the interface yet. The opening should establish the physical problem
and let the moving pantograph create curiosity.

### 0:25–0:58 — Explain the project and establish credibility

**Actions**

1. Point once to the amber **PASSIVE** lane card.
2. Point once to the cyan **AeroPINN** lane card.
3. Move down to the contact-force graph and trace from the passive legend to the active
   legend.
4. At approximately 0:42, click **VALIDATION** in the top bar.
5. Pause on **PHYSICAL FIDELITY STATUS** and
   **LIVE MODAL MODEL · CROSS-MODEL CONSISTENCY**.
6. Scroll far enough to reveal **EN 50318 REFERENCE CHECK** and the
   **PINN PREDICTION vs CLASSICAL SOLVER** heading.

**Speaker**

> Both lanes receive the same external disturbance. The passive lane has no active
> force; the AeroPINN lane uses delayed sensors, an estimator, predictive control, and
> an explicit actuator model. A physics-informed neural network predicts the response,
> but a separate model-predictive controller chooses the command. We expose reference,
> cross-model, prediction-error, and timing checks—and we clearly label this as
> simulation evidence, not railway certification.

**Editing note**

Use a gentle digital zoom on the validation headings. Do not wait for the viewer to
read every table row.

### 0:58–1:28 — State the exact task

**Actions**

1. Hard-cut to View B, the full-screen task slide.
2. Highlight “communication,” then “core workflow,” then “accessibility need.”
3. Keep the slide still for the remainder of this segment.

**Speaker**

> Our challenge was: improve the part of our existing MVP most related to
> communication, make a core workflow usable for people with at least one
> accessibility need, and demonstrate it with realistic sample data or a plausible
> scenario. The key question was not, “How do we add a random accessibility feature?”
> It was, “What information is AeroPINN already trying to communicate, and who cannot
> currently use it?”

**On-screen overlay**

`Communication → core workflow → equivalent access`

### 1:28–2:08 — Explain the interpretation of accessibility

**Actions**

1. Keep the task slide visible for the first sentence.
2. Hard-cut back to View A and close Validation with the **✕** button.
3. Move the pointer across the moving 3D scene and fast force chart once.
4. Stop the pointer over **JOURNEY LOGS**, but do not open it yet.

**Speaker**

> AeroPINN is designed to operate autonomously. A human is not supposed to steer the
> pantograph from this dashboard. The real human workflow is after the journey:
> finding a run, understanding what happened, checking the controller’s evidence, and
> sharing that evidence for engineering or research.
>
> Before our improvement, that communication was visually locked inside a moving 3D
> scene and a high-speed graph. A blind or low-vision screen-reader user cannot inspect
> that graph. It can also overwhelm someone who needs more processing time, and it
> demands hardware capable of rendering the scene. So we made the existing telemetry
> persistent, textual, documented, and exportable.

**Critical wording**

Say “the core workflow is after the journey” slowly. This is the central reasoning
that connects an autonomous system to the accessibility task.

### 2:08–2:55 — Demonstrate a plausible cause-and-effect scenario

**Actions**

1. Move to the Operator Console.
2. Click **▲ STRESS TEST** once.
3. Let the sliders animate to 350 km/h, 50% tension, and 3.5× turbulence.
4. Pause for three seconds while the force trace changes.
5. Click **GUST** once.
6. Point to the passive/active force trace and then the **FORCE σ** and **ARC TIME**
   comparison.
7. Briefly point to **CMD** and **APPLIED** to show that requested and applied force are
   distinct.

**Speaker**

> Here is our plausible demonstration scenario. The train enters a high-wind section
> at 350 kilometres per hour, wire tension falls to fifty percent, and turbulence rises
> to three-and-a-half times nominal. Now we inject a transient gust. The passive and
> active responses diverge, the controller requests a bounded correction, and the
> actuator applies it with modeled delay. These live visuals explain the event in the
> moment—but an auditor should not have to notice, remember, or screenshot a spike as
> it happens.

**Success cue**

The force trace should visibly react after **GUST**. Exact values vary with the rolling
window; never promise a specific number in the narration.

**Fallback**

If the live trace stalls, cut to a previously captured five-second stress-test clip and
continue the same narration. Do not restart the backend on camera.

### 2:55–3:40 — Open the automatic journey audit

**Actions**

1. Click **JOURNEY LOGS** in the top bar.
2. Let focus visibly land in the dialog.
3. In the left catalogue, click the completed **High-wind contact stress test**.
4. Pause on **ACCESSIBLE JOURNEY SUMMARY**.
5. Point to Session ID, status, start time, sample count, event count, distance, stored
   data, and command-limit duty.
6. Point to the passive-versus-AeroPINN contact-force summary table.

**Speaker**

> Every WebSocket simulation is logged automatically on the backend; there is no
> record button an operator can forget. Each journey receives a stable ID, UTC times,
> route position, train and scenario documentation, summary statistics, and indexed
> events. The catalogue persists across restarts, and interrupted runs remain visible.
>
> This completed high-wind sample follows the same production simulation path we just
> used. Its outcomes are calculated by the engine, while the scenario itself is
> deterministic and repeatable for judging.

**Accessibility note for the speaker**

> This dialog uses headings, labels, tables, keyboard focus, an Escape close action,
> and live status announcements. More importantly, the evidence is no longer dependent
> on perceiving the 3D scene.

This last sentence may be spoken while moving into the next segment; do not pause long
enough to exceed 3:40.

### 3:40–4:38 — Show how detailed the records are

**Actions**

1. Scroll to **VIEW LOGGED DATA**.
2. Click **EVENTS**.
3. Pause on a gust, contact-loss, estimator-fallback, scenario-input, or lifecycle event.
4. Expand **View complete raw record** for one event, then collapse it.
5. Click **PHYSICS 1 KHZ**.
6. Point to speed, passive force, AeroPINN force, and command.
7. Expand one raw physics record for two seconds; scroll within it just enough to show
   head/frame motion, wire ripple, estimator, timing, and sensors. Collapse it.
8. Click **CONSTANTS 1 HZ**.
9. Point to setpoint, integration step, contact tension, and actuator response.
10. Expand one constants record and show that pantograph, catenary, sensor, actuator,
    controller, PINN, solver, and operating configuration are nested inside.
11. Click **NEXT PAGE** once, then **PREVIOUS PAGE**, proving bounded pagination.

**Speaker**

> We preserve four complementary forms of evidence. Events explain what changed.
> Native one-kilohertz physics records preserve force, motion, ripple, estimator,
> actuator, sensor, and timing values. Complete dashboard frames are stored at about
> thirty hertz. And once per second, we snapshot the constants needed to interpret and
> reproduce the run—from pantograph and catenary parameters to controller weights and
> integration settings.
>
> Long files are browsed as bounded text pages, so a low-resource device never has to
> load an entire journey. Nothing important is hidden behind only a green score or a
> polished animation.

**Time-saving cut**

If behind schedule, skip expanding the event record. Always show both **PHYSICS 1 KHZ**
and **CONSTANTS 1 HZ**; they are the strongest proof of detailed, non-black-box logging.

### 4:38–5:20 — Demonstrate exports and journey documentation

**Actions in the browser**

1. Scroll to **DOWNLOAD DATA**.
2. Click **CSV EXPORT**.
3. Click **JSON EXPORT**.
4. Click **AUDIT PACKAGE (.ZIP)**.
5. Point to the three format explanations while downloads begin.
6. Scroll to **JOURNEY DOCUMENTATION**.
7. Point down the form: train ID, route, origin/destination, direction, track,
   chainage, GPS, temperatures, wind, weather, and scenario.
8. In **Route name**, press `Ctrl+A` and type `Pune High-Speed Test Corridor`.
9. Click **SAVE DOCUMENTATION** and pause until the status announces that metadata was
   saved.

**Hard-cut to View C**

10. Show the extracted ZIP in list view.
11. Highlight `physics_1khz.csv`, `dashboard_30hz.csv`, `constants_1hz.csv`,
    `telemetry.json`, `events.json`, `summary.json`, `data_dictionary.md`, and
    `manifest.json`.
12. Open `data_dictionary.md` briefly, then `manifest.json` and highlight a SHA-256
    hash.

**Speaker**

> The same evidence can leave the dashboard in three forms. CSV provides flat,
> screen-reader- and spreadsheet-friendly columns. JSON preserves the complete nested
> structure. The audit package includes both, separates the native rates, adds the
> constants, summary, event log, data dictionary, instructions, and a manifest with
> SHA-256 integrity hashes.
>
> Journey documentation is editable because a useful record needs context: which
> train, route, direction, track, position, date, temperatures, wind, weather, and
> scenario produced the reading. This turns transient telemetry into evidence another
> person can understand and reuse asynchronously.

**Presenter note**

The date is captured automatically in UTC; do not search for a date input in the form.
The route/GPS values are documentation attached to the plausible scenario.

### 5:20–5:50 — Explain why this is the best fit for the task

**Visual**

- Use a split screen: dashboard on the left, audit folder on the right.
- Add three short overlay phrases one at a time:
  1. `Existing telemetry—not a separate feature`
  2. `Equivalent detail—not a simplified summary`
  3. `Persistent · self-paced · portable`

**Speaker**

> We believe this is the strongest fit for the task because it improves the project’s
> existing communication layer rather than inventing an unrelated workflow. It gives
> equivalent access to the underlying information, not only a simplified summary. It
> matches the real human role in an autonomous system: audit, validation, documentation,
> and research after a journey. And because the result is persistent and portable, the
> user can work at their own pace with a screen reader, spreadsheet, script,
> sonification tool, or lower-powered device.

### 5:50–6:05 — Close with the outcome

**Actions**

1. Hard-cut back to the dashboard.
2. If Journey Logs is still open, press `Escape` to close it, visibly demonstrating
   keyboard operation.
3. Click **◇ NOMINAL** so the controls return toward their baseline.
4. End on the moving pantograph and the AeroPINN logo.

**Speaker**

> AeroPINN already generated the evidence. Our improvement makes sure that evidence
> can be found, understood, verified, and shared by more people. That is how we made
> the project’s core communication workflow accessible without changing the autonomous
> purpose of the system.

**End card**

```text
AeroPINN
From live simulation to accessible engineering evidence
CSV · JSON · complete audit package
```

Hold the end card for two seconds without narration.

## Full narration-only version

Use this section for teleprompter import. Screen directions are intentionally omitted.

> At high speed, a train’s pantograph must maintain stable contact with the overhead
> wire. Too little force causes separation and arcing; too much force increases wear.
> AeroPINN is our research simulation of an active pantograph that predicts this
> interaction and responds before contact becomes unstable.
>
> Both lanes receive the same external disturbance. The passive lane has no active
> force; the AeroPINN lane uses delayed sensors, an estimator, predictive control, and
> an explicit actuator model. A physics-informed neural network predicts the response,
> but a separate model-predictive controller chooses the command. We expose reference,
> cross-model, prediction-error, and timing checks—and we clearly label this as
> simulation evidence, not railway certification.
>
> Our challenge was: improve the part of our existing MVP most related to
> communication, make a core workflow usable for people with at least one
> accessibility need, and demonstrate it with realistic sample data or a plausible
> scenario. The key question was not, “How do we add a random accessibility feature?”
> It was, “What information is AeroPINN already trying to communicate, and who cannot
> currently use it?”
>
> AeroPINN is designed to operate autonomously. A human is not supposed to steer the
> pantograph from this dashboard. The real human workflow is after the journey:
> finding a run, understanding what happened, checking the controller’s evidence, and
> sharing that evidence for engineering or research.
>
> Before our improvement, that communication was visually locked inside a moving 3D
> scene and a high-speed graph. A blind or low-vision screen-reader user cannot inspect
> that graph. It can also overwhelm someone who needs more processing time, and it
> demands hardware capable of rendering the scene. So we made the existing telemetry
> persistent, textual, documented, and exportable.
>
> Here is our plausible demonstration scenario. The train enters a high-wind section
> at 350 kilometres per hour, wire tension falls to fifty percent, and turbulence rises
> to three-and-a-half times nominal. Now we inject a transient gust. The passive and
> active responses diverge, the controller requests a bounded correction, and the
> actuator applies it with modeled delay. These live visuals explain the event in the
> moment—but an auditor should not have to notice, remember, or screenshot a spike as
> it happens.
>
> Every WebSocket simulation is logged automatically on the backend; there is no
> record button an operator can forget. Each journey receives a stable ID, UTC times,
> route position, train and scenario documentation, summary statistics, and indexed
> events. The catalogue persists across restarts, and interrupted runs remain visible.
>
> This completed high-wind sample follows the same production simulation path we just
> used. Its outcomes are calculated by the engine, while the scenario itself is
> deterministic and repeatable for judging. This dialog uses headings, labels, tables,
> keyboard focus, an Escape close action, and live status announcements. More
> importantly, the evidence is no longer dependent on perceiving the 3D scene.
>
> We preserve four complementary forms of evidence. Events explain what changed.
> Native one-kilohertz physics records preserve force, motion, ripple, estimator,
> actuator, sensor, and timing values. Complete dashboard frames are stored at about
> thirty hertz. And once per second, we snapshot the constants needed to interpret and
> reproduce the run—from pantograph and catenary parameters to controller weights and
> integration settings.
>
> Long files are browsed as bounded text pages, so a low-resource device never has to
> load an entire journey. Nothing important is hidden behind only a green score or a
> polished animation.
>
> The same evidence can leave the dashboard in three forms. CSV provides flat,
> screen-reader- and spreadsheet-friendly columns. JSON preserves the complete nested
> structure. The audit package includes both, separates the native rates, adds the
> constants, summary, event log, data dictionary, instructions, and a manifest with
> SHA-256 integrity hashes.
>
> Journey documentation is editable because a useful record needs context: which
> train, route, direction, track, position, date, temperatures, wind, weather, and
> scenario produced the reading. This turns transient telemetry into evidence another
> person can understand and reuse asynchronously.
>
> We believe this is the strongest fit for the task because it improves the project’s
> existing communication layer rather than inventing an unrelated workflow. It gives
> equivalent access to the underlying information, not only a simplified summary. It
> matches the real human role in an autonomous system: audit, validation, documentation,
> and research after a journey. And because the result is persistent and portable, the
> user can work at their own pace with a screen reader, spreadsheet, script,
> sonification tool, or lower-powered device.
>
> AeroPINN already generated the evidence. Our improvement makes sure that evidence
> can be found, understood, verified, and shared by more people. That is how we made
> the project’s core communication workflow accessible without changing the autonomous
> purpose of the system.

## Rehearsal scorecard

After a dry run, confirm:

- Total duration is between 5:50 and 6:10.
- The exact challenge statement is visible and spoken.
- “Blind or low-vision screen-reader user” is named explicitly.
- “Post-journey audit” is identified as the core workflow.
- The demo shows Stress Test and Gust, not only static screenshots.
- The Journey Logs sample is completed and readable.
- Events, Physics 1 kHz, and Constants 1 Hz are all shown.
- CSV, JSON, and Audit Package buttons are clicked.
- Route/scenario documentation is shown and saved.
- The audit folder, data dictionary, and integrity hashes are visible.
- Simulation/reference-check limits are stated honestly.
- No personal paths, credentials, unrelated tabs, or notifications appear.
- The final sentence ends before the six-minute limit.

## Emergency 20-second cuts

If the first take runs long, cut in this order:

1. Skip expanding the raw event record: saves about 8 seconds.
2. Show only the headings in Validation instead of scrolling to the overlay: saves
   about 6 seconds.
3. Do not click Previous Page after showing Next Page: saves about 3 seconds.
4. Shorten the file shot to `constants_1hz.csv`, `data_dictionary.md`, and
   `manifest.json`: saves about 5 seconds.

Do not cut the assigned task, accessibility interpretation, 1 kHz physics view,
constants view, export formats, or “why this fits” conclusion.
