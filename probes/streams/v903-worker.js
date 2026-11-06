/* V903 worker: run one tee() case in a dedicated worker realm.
 * The main page keeps its own timer, so:
 *   - whole WebProcess dies      -> main thread never beacons V903-MAIN-ALIVE
 *   - only this worker spins/lives -> V903-MAIN-ALIVE arrives, worker is terminated
 */
'use strict';

function qs(name) {
  var m = new RegExp('[?&]' + name + '=([^&]+)').exec(location.search);
  return m ? decodeURIComponent(m[1]) : '';
}

var CASE = qs('case') || 'w_y2';
var RUN = qs('run') || 'norun';

function bks(tag, body) {
  var u = '/beacon/V903-' + tag + '?d=' +
          encodeURIComponent(String(body == null ? '' : body).slice(0, 440)) +
          '&run=' + encodeURIComponent(RUN) + '&t=' + Date.now() + '&s=1';
  try { var x = new XMLHttpRequest(); x.open('GET', u, false); x.send(null); }
  catch (e) { try { var i = new Image(); i.src = u; } catch (e2) {} }
}

function mkStream() {
  return new ReadableStream({ start: function () {}, pull: function () {}, cancel: function () {} });
}
function plainTee() {
  return new ReadableStream({ start: function (c) { c.close(); } }).tee();
}
function errOf(e) {
  return e ? String(e.name || 'Error') + ':' + String(e.message || '').slice(0, 90) : 'none';
}

function mkRes(ctx, v, d) {
  var o = {};
  Object.defineProperty(o, 'value', {
    get: function () { ctx.valRead++; return v; }, enumerable: true, configurable: true
  });
  Object.defineProperty(o, 'done', {
    get: function () { ctx.doneRead++; return d; }, enumerable: true, configurable: true
  });
  return o;
}

function stage(ctx, s, extra) {
  if (ctx.next <= 3 || !ctx.limited) bks('W-STAGE', CASE + ':' + s + (extra ? ':' + extra : '') + ':' + RUN);
  ctx.last = s + (extra ? ':' + extra : '');
}

function iterOf(ctx, values, opts) {
  opts = opts || {};
  var i = 0;
  return {
    next: function () {
      var n = ++ctx.next;
      stage(ctx, 'N' + n + '-pre');
      if (i < values.length) {
        var v = values[i++];
        stage(ctx, 'N' + n + '-ret', 'done=false,t=' + (typeof v));
        return mkRes(ctx, v, false);
      }
      if (opts.infinite) {
        stage(ctx, 'N' + n + '-ret', 'done=false,inf');
        return mkRes(ctx, { inf: n }, false);
      }
      stage(ctx, 'N' + n + '-ret', 'done=true');
      return mkRes(ctx, undefined, true);
    },
    'return': function () { ctx.ret++; stage(ctx, 'RET'); return { done: true }; }
  };
}

function spec(id) {
  if (id === 'w_y2') return { values: [mkStream(), mkStream()], opts: {} };
  if (id === 'w_y1') return { values: [{ a: 1 }], opts: {} };
  if (id === 'w_y1inf') return { values: [{ a: 1 }], opts: { infinite: true, limited: true } };
  return null;
}

function run() {
  bks('W-START', 'case=' + CASE + ',run=' + RUN);
  if (typeof ReadableStream === 'undefined') { bks('W-NORS', CASE + ':' + RUN); return; }

  var ctx = { iter: 0, next: 0, valRead: 0, doneRead: 0, ret: 0, last: 'S0', limited: false };
  var sp = spec(CASE);
  if (!sp) { bks('W-SKIP', 'case=' + CASE); return; }
  ctx.limited = !!sp.opts.limited;

  var saved = Array.prototype[Symbol.iterator];
  Array.prototype[Symbol.iterator] = function () {
    ctx.iter++;
    bks('W-STAGE', CASE + ':S2-iterfn:' + RUN);
    return iterOf(ctx, sp.values, sp.opts);
  };

  bks('W-STAGE', CASE + ':S3-before-tee:' + RUN);
  var z = null, err = 'none';
  try { z = plainTee(); } catch (e) { err = errOf(e); }
  bks('W-STAGE', CASE + ':S4-after-tee:len=' + (z ? z.length : 'null') + ',err=' + err + ':' + RUN);

  try { Array.prototype[Symbol.iterator] = saved; } catch (e) {}
  if (z) {
    try { z[0] && z[0].cancel(); } catch (e) {}
    try { z[1] && z[1].cancel(); } catch (e) {}
  }

  var detail = 'err=' + err + ',it=' + ctx.iter + ',next=' + ctx.next +
               ',valRead=' + ctx.valRead + ',doneRead=' + ctx.doneRead + ',ret=' + ctx.ret;
  bks('W-DONE', CASE + ',' + detail + ',' + RUN);
  try { postMessage({ 'case': CASE, tag: (err === 'none') ? 'OK' : 'THROW', detail: detail }); } catch (e) {}
}

try { run(); } catch (e) { bks('W-FATAL', CASE + ':' + errOf(e) + ':' + RUN); }
