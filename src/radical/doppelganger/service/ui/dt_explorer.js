/* ==========================================================================
 *  dt_explorer.js -- the `dt` plugin's UI module for the ORBIT Explorer.
 *
 *  ORBIT's plugin-UI contract is one ES module per plugin, served at
 *  `/plugins/<plugin_name>.js` from the class attribute `Plugin.ui_module`
 *  (broker-hosted plugins only -- `BrokerPluginHost.get_ui_modules()` is
 *  the only reader).  The Explorer imports it, drops `template()` into a
 *  page and calls `init(page, api)`; the module runs same-origin in the
 *  Explorer's own scope, so a canvas is entirely fine.
 *
 *  This file is an adapter, not a second dashboard: the implementation is
 *  `dt_dash.js`, which the plugin also serves (`GET {ns}/ui/dt_dash.js`)
 *  and which the standalone page loads with a plain <script src>.  It has
 *  no imports and no exports, so importing it here as a module and loading
 *  it there as a classic script are both valid; either way it publishes
 *  `window.DTDash`.
 *
 *  Live data comes from the same two places in both hosts -- the 1 Hz
 *  `admin/sessions` poll and the gateway's SSE feed.  The dashboard opens
 *  its own EventSource rather than using the Explorer's `onNotification`
 *  hook, because that hook only delivers *this* plugin's events, and the
 *  simulation tiles are rhapsody's.
 * ========================================================================*/

export const name = 'dt';

export function template() {
  return `
    <div class="page-header">
      <div class="page-icon">🪞</div>
      <h2>Digital Twins — <span class="endpoint-label"></span></h2>
    </div>
    <div class="card" id="dt-dash-card">
      <div id="dt-dash-host" style="height: 640px; min-height: 320px;"></div>
    </div>
  `;
}

export function css() {
  // dt_dash.js injects its own stylesheet once, so there is nothing to
  // duplicate here.
  return '';
}

export async function init(page, api) {
  const host = page.querySelector('#dt-dash-host');
  if (!host) return;

  const dtPath = `/${api.endpointName}/${api.pluginName}`;

  try {
    if (!window.DTDash) {
      await import(`${api.brokerUrl}${dtPath}/ui/dt_dash.js`);
    }
  } catch (exc) {
    host.innerHTML = `<p style="color:var(--muted)">dashboard unavailable:`
                   + ` ${api.escHtml(String(exc))}</p>`;
    return;
  }

  // Same origin as the Explorer, so the broker's auth cookie rides along
  // and no token is needed here.
  page._dtDash = window.DTDash.mount(host, {
    brokerUrl: api.brokerUrl,
    dtPath,
    live:      true,
    compact:   true,
  });
}

export function onNotification() {
  // The dashboard subscribes to the SSE feed itself -- see the header.
}
