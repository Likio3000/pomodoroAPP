# Design specification

Direction: a quiet editorial focus tool. English and Spanish interface, chalk (#f7f8f2), forest (#233f35), muted text (#68746f), hairline borders (#ced4cb). No gradients or imagery. Native text and vector controls. Serif Georgia for the wordmark and editorial headings; deliberately chosen system sans-serif for controls and tabular timer numerals.

Primary screen: header with senda., Enfoque, Progreso and Ajustes, plus a compact ES / EN selector. Two-thirds focus canvas and one-third task rail. One circular dial, three modes, start/pause and reset controls. Open metrics strip underneath. Primary copy: Una cosa a la vez. / Haz espacio para lo importante. / TODO EMPIEZA AQUÍ / Comenzar. Task copy: Tu siguiente paso / Una lista corta. Una mente más libre. / ¿En qué vas a trabajar? / Empieza con una intención. / Añade una tarea y dale tu atención. Goal: Tu ritmo de hoy / 0 de 4 sesiones / Cada sesión cuenta.

Progress extends the same system: open metrics, seven-day chart, dated session rows, CSV export. Settings is an accessible native dialog with duration fields, daily goal, sound and backup controls. Timer completion uses a calm confirmation panel with an explicit next action. No automatic chained sessions. Mobile collapses to one column, reduces the ring, keeps all controls usable and stacks the rail below. Reduced motion is respected.

Concept created with the built-in Image Gen tool before implementation, with the prompt to render the complete timer, task rail, zero-state metrics and navigation as a native web app. The concept is a design reference, not a runtime asset. Responsive and functional state copy extend the system as required. The small footer clarifies local storage, and daily metric labels explicitly say “hoy” to distinguish them from cumulative history.

The Senda wordmark replaces the old product name without changing the visual system. Both languages use complete sentence templates for dynamic messages. User-authored tasks are never translated. Language is an optional version 2 data field, preserving existing storage keys and backup compatibility.
