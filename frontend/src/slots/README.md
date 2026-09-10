# UI slots

Slots are named extension points where cowork-projects (bundles and plugins) can add panels without
touching the host pages.

| Slot name       | Rendered where                                         | Context fields            |
| --------------- | ------------------------------------------------------ | ------------------------- |
| `chat.sidebar`  | Bottom of the conversation sidebar                     | `conversationId`          |
| `chat.header`   | Right side of the conversation header                  | `conversationId`, `bundle`|
| `project.panel` | Project detail page, under the settings card           | `projectId`, `bundle`     |
| `admin.nav`     | Extra links in the admin navigation                    | —                         |

## Registering a panel

```ts
import { registerSlot } from '@/slots'

registerSlot('project.panel', {
  id: 'my-kpi-panel',                      // stable id; re-registering replaces it (HMR friendly)
  component: MyKpiPanel,                   // React component receiving SlotContext as props
  when: (ctx) => ctx.bundle?.manifest.ui_slots?.includes('kpi-panel'),  // optional predicate
  order: 10,                               // optional sort order
})
```

`registerSlot` returns an unregister function. `<Slot name="project.panel" context={{ projectId, bundle }} />`
renders every registration whose `when` predicate passes, in `order`.

## Bundle-driven panels

A project bundle (`GET /v1/bundles`) has a `manifest`. When the manifest's `ui_slots` array contains
`"kpi-panel"`, the built-in `KpiPanel` demo (registered in `slots/index.ts`) appears on that project's page.
Add your own by registering a component whose `when` predicate checks for your slot key in
`ctx.bundle.manifest.ui_slots`.

## Adding a new slot name

Extend the `SlotName` union in `registry.ts` and place a `<Slot name="…"/>` in the host page. Keep the
`SlotContext` fields documented in the table above.
