const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync('index.html', 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
class Element {
  constructor(tag = 'div') { this.tagName = tag; this.children = []; this.attrs = {}; this.dataset = {}; this.hidden = false; this.textContent = ''; this.className = ''; this.classList = { add: value => this.className += ' ' + value }; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(key, value) { this.attrs[key] = value; }
  remove() { this.removed = true; }
  focus() { this.focused = true; }
  select() { this.selected = true; }
  scrollIntoView() { this.scrolled = true; }
}
const walk = node => [node, ...node.children.flatMap(walk)];
async function page(csv, opts = {}) {
  const nodes = Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(m => [m[1], new Element()]));
  nodes.sort.value = opts.view || 'priority';
  nodes['copy-fallback'].hidden = true;
  const root = new Element('html');
  const errors = [];
  const stored = {};
  const copies = [];
  const intervals = [];
  let sharedClaims = [];
  const context = vm.createContext({
    URL, URLSearchParams, crypto: require('node:crypto').webcrypto,
    setInterval: (fn, delay) => intervals.push({fn, delay}),
    console: { assert: (ok, msg) => {if (!ok) errors.push(msg);}, error: (...args) => errors.push(args)},
    location: {href:opts.url || 'https://example.test/wishlist/', hash: opts.hash || ''},
    document: {documentElement:root, createElement: tag => new Element(tag), getElementById: id => nodes[id] || walk(nodes.grid).find(n => n.id === id)},
    window: { addEventListener: () => {} },
    localStorage: {getItem: key => { if (opts.storageBlocked) throw Error(); return key === 'wishlist-theme' ? opts.theme : null; }, setItem: (k,v) => { if (opts.storageBlocked) throw Error(); stored[k] = v; }},
    navigator: {clipboard: {writeText: async value => { if (opts.clipboardBlocked) throw Error(); copies.push(value); }}},
    fetch: async (url, request) => {
      if (url === 'api/claims') {
        assert.ok(!opts.noAPI, 'Static Pages must not call the claims API');
        if (request?.method === 'POST') { const data = JSON.parse(request.body); sharedClaims = data.action === 'claim' ? [data.item] : []; }
        return {ok:true, json:async () => ({claims:sharedClaims})};
      }
      if (url === 'prices.json') {
        assert.equal(request.cache, 'no-store');
        if (opts.pricesFailed) throw Error('offline');
        return {ok:Boolean(opts.prices), json:async () => opts.prices};
      }
      assert.equal(url,'items.csv');
      assert.equal(request.cache,'no-cache');
      if (opts.fetchFailed) throw Error();
      return {ok: true, text: async () => csv};
    }
  });
  for (const script of scripts) vm.runInContext(script, context);
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(errors, []);
  return {nodes, root, stored, copies, intervals, run: code => vm.runInContext(code, context)};
}
(async () => {
  const csv = fs.readFileSync('items.csv','utf8');
  const legacyCSV = fs.readFileSync('tests/fixtures/legacy.csv','utf8');
  const actual = await page(csv);
  const publicPage = await page(csv, {url:'https://onelosthero.github.io/Wishlist/', noAPI:true});
  assert.ok(!walk(publicPage.nodes.grid).some(n => n.className === 'button claim'));
  assert.equal(publicPage.nodes['claim-help'].hidden, false);
  assert.equal(publicPage.run('shareURL()'), 'https://onelosthero.github.io/Wishlist/');
  const legacy = await page(legacyCSV);
  const actualItems = actual.run('readItems(' + JSON.stringify(csv) + ')');
  const legacyItems = legacy.run('readItems(' + JSON.stringify(legacyCSV) + ')');
  for (const key of ['name','note','image']) assert.equal(actualItems[0][key], legacyItems[0][key]);
  assert.equal(actualItems[0].link, legacyItems[0].link + '?currency=USD');
  assert.equal(actual.nodes.grid.children.length,actualItems.length);
  assert.equal(legacy.nodes.grid.children.length,1);
  assert.equal(legacyItems[0].priority,2);
  assert.equal(legacyItems[0].status,'');
  assert.equal(legacyItems[0].category,'');
  assert.equal(legacy.root.dataset.theme,undefined);
  assert.equal(legacy.nodes.title.textContent,"Ryan's wishlist");
  assert.ok(walk(actual.nodes.grid).some(n => n.className === 'ribbon'));
  assert.ok(!walk(legacy.nodes.grid).some(n => n.className === 'ribbon'));
  for (const cls of ['note','product']) assert.equal(walk(actual.nodes.grid).find(n => n.className === cls).textContent, walk(legacy.nodes.grid).find(n => n.className === cls).textContent);
  assert.equal(walk(legacy.nodes.grid).find(n => n.className === 'tag').textContent, '$856 CAD');
  assert.equal(walk(actual.nodes.grid).find(n => n.tagName === 'img').src, legacyItems[0].image);
  actual.nodes.theme.onclick(); assert.equal(actual.root.dataset.theme,'light'); assert.equal(actual.stored['wishlist-theme'],'light');
  assert.equal((await page(csv,{theme:'light'})).root.dataset.theme,'light');
  assert.equal((await page(csv,{theme:'unexpected'})).root.dataset.theme,undefined);
  const blocked = await page(csv,{storageBlocked:true,clipboardBlocked:true});
  blocked.nodes.theme.onclick(); assert.equal(blocked.root.dataset.theme,'light');
  await blocked.run('copyLink("https://example.test/#item-test")');
  assert.equal(blocked.nodes['copy-fallback'].hidden,false);
  assert.equal(blocked.nodes['copy-value'].value,'https://example.test/#item-test');
  const fixture = 'status,image,priority,category,link,note,price,name\r\n' +
    'claimed,photo.jpg,1,Books,https://example.test,"Quoted, ""note""",$1,Claimed\r\n' +
    ',,3,Home,,,any amount,Unknown\r\n' +
    ',,2,Books,,,"$1,200.50",Expensive\r\n' +
    ',,1,Books,,,~$30–50,Wanted\r\n' +
    ',,2,Home,,,under $25,Cheap\r\n' +
    'bought,photo.jpg,2,Home,,,any amount,Bought\r\n' +
    ',,2,Home,,,€.75,Decimal\r\n';
  const test = await page(fixture);
  const names = () => test.nodes.grid.children.map(c => walk(c).find(n => n.tagName === 'h2').textContent);
  assert.deepEqual(names(),['Wanted','Expensive','Cheap','Decimal','Unknown','Claimed','Bought']);
  test.nodes.sort.value='low'; test.nodes.sort.onchange();
  assert.deepEqual(names(),['Decimal','Cheap','Wanted','Expensive','Unknown','Claimed','Bought']);
  test.nodes.sort.value='high'; test.nodes.sort.onchange();
  assert.deepEqual(names(),['Expensive','Wanted','Cheap','Decimal','Unknown','Claimed','Bought']);
  test.nodes.categories.children.find(c => c.textContent === 'Books').onclick();
  assert.deepEqual(names(),['Expensive','Wanted','Claimed']);
  assert.equal(test.nodes.categories.children.find(c => c.textContent === 'Books').attrs['aria-pressed'],'true');
  test.nodes.categories.children[0].onclick();
  for (const card of test.nodes.grid.children.filter(c => c.className.includes('unavailable'))) {
    assert.ok(walk(card).some(n => n.className === 'stamp'));
    assert.ok(!walk(card).some(n => n.className.includes('claim')));
  }
  assert.ok(html.includes('.card.unavailable img { filter: grayscale(1)'));
  const copy = walk(actual.nodes.grid).find(n => n.className === 'copy');
  await copy.onclick(); assert.equal(actual.copies[0],'https://example.test/wishlist/#item-majora-s-mask-wooden-replica');
  const claimButton = walk(actual.nodes.grid).find(n => n.className === 'button claim');
  assert.equal(claimButton.textContent, 'I might get this');
  assert.equal(claimButton.disabled, false);
  await claimButton.onclick();
  assert.ok(walk(actual.nodes.grid).some(n => n.textContent === 'Possibly taken'));
  const undoButton = walk(actual.nodes.grid).find(n => n.textContent === 'Undo my mark');
  await undoButton.onclick();
  assert.ok(!walk(actual.nodes.grid).some(n => n.textContent === 'Possibly taken'));
  actual.run('CONFIG.contact = "mailto:ryan@example.test?cc=friend%40example.test"');
  const mail = actual.run('contactURL("Gift & thanks")');
  assert.equal(new URL(mail).searchParams.get('body'),'Gift & thanks');
  assert.equal(new URL(mail).searchParams.get('subject'),"Ryan's wishlist");
  assert.equal(new URL(mail).searchParams.get('cc'),'friend@example.test');
  actual.run('CONFIG.shareURL = "https://example.test/Published/"');
  assert.equal(actual.run('shareURL("item-gift")'),'https://example.test/Published/#item-gift');
  const anchor = await page(fixture,{hash:'#item-wanted'});
  assert.ok(anchor.nodes.grid.children.find(c => c.id === 'item-wanted').scrolled);
  const duplicate = test.run('readItems("name\\nGift\\nGift\\nGift-2\\n🎁")');
  assert.equal(new Set(duplicate.map(i => i.slug)).size,4);
  assert.equal(test.run('parseCSV(\'a,"line 1\\nline 2",c\\r\\n\')[0][1]'),'line 1\nline 2');
  const empty = await page('name,price,note,link,image\n'); assert.equal(empty.nodes.count.textContent,'No wishes just yet. Check back soon.');
  const failed = await page('',{fetchFailed:true}); assert.ok(failed.nodes.count.textContent.startsWith("Couldn't load"));
  const autoCSV = 'name,price,link,price_source,status\nShop,$999,https://shop.test/products/a,shopify,\nAmazon,$999,https://www.amazon.com/dp/B08KG4QVCT/?tag=owner-20,amazon,\nManual,$30,,,\nClaimed,,https://shop.test/products/b,shopify,claimed\n';
  const now = Date.now();
  const fresh = {status:'ok',source:'shopify',amount:119,currency:'USD',checked_at:new Date(now - 60000).toISOString(),expires_at:new Date(now + 3600000).toISOString()};
  const prices = {version:1,items:{
    'https://shop.test/products/a':fresh,
    'https://www.amazon.com/dp/B08KG4QVCT/?tag=owner-20':{...fresh,source:'amazon',amount:249.99},
    'https://shop.test/products/b':{...fresh,amount:1}
  }};
  const live = await page(autoCSV,{prices});
  assert.deepEqual(walk(live.nodes.grid).filter(n => n.className === 'tag').map(n => n.textContent), ['$119.00 USD','$249.99 USD','$30','$1.00 USD']);
  assert.ok(walk(live.nodes.grid).some(n => n.tagName === 'time' && n.attrs.datetime === fresh.checked_at));
  assert.ok(walk(live.nodes.grid).some(n => n.tagName === 'summary' && n.textContent === 'Price details'));
  const amazonCard = live.nodes.grid.children[1];
  assert.ok(walk(amazonCard).find(n => n.className === 'product').href.endsWith('tag=owner-20'));
  live.nodes.sort.value='low'; live.nodes.sort.onchange();
  assert.deepEqual(live.nodes.grid.children.map(c => walk(c).find(n => n.tagName === 'h2').textContent), ['Manual','Shop','Amazon','Claimed']);
  for (const overrides of [
    {expires_at:new Date(now - 1).toISOString()},
    {checked_at:new Date(now - 25*3600000).toISOString()},
    {checked_at:'broken'}, {checked_at:new Date(now + 3600000).toISOString()},
    {amount:0}, {amount:'119'}, {currency:'bad'}, {currency:'CAD'}, {status:'unavailable'}, {source:'amazon'}
  ]) {
    const invalid = await page(autoCSV,{prices:{version:1,items:{'https://shop.test/products/a':{...fresh,...overrides}}}});
    assert.ok(walk(invalid.nodes.grid.children[0]).some(n => n.textContent === 'Check price at the store'));
    assert.ok(!walk(invalid.nodes.grid).some(n => n.textContent.includes('$999')));
  }
  const from = await page(autoCSV,{prices:{version:1,items:{'https://shop.test/products/a':{...fresh,from:true,estimate:true,original_currency:'CAD',fx_date:'2026-10-09'}}}});
  assert.ok(walk(from.nodes.grid).some(n => n.textContent === 'From ≈ $119.00 USD'));
  assert.ok(walk(from.nodes.grid).some(n => n.textContent === 'USD estimate; store charges CAD. Exchange rate dated 2026-10-09.'));
  for (const opts of [{pricesFailed:true},{prices:{version:2,items:{}}}]) {
    const fallback = await page(autoCSV,opts);
    assert.equal(fallback.nodes.grid.children.length,4);
    assert.ok(walk(fallback.nodes.grid).some(n => n.textContent === 'Check price on Amazon'));
    assert.ok(walk(fallback.nodes.grid).some(n => n.textContent === '$30'));
  }
  // Preserve the original flat views above, and exercise the new default separately.
  assert.match(html, /id="sort"><option value="sections">/);
  const cardNames = node => walk(node).filter(n => n.tagName === 'article').map(card => walk(card).find(n => n.className === 'card-title').textContent);
  const sectionCSV = [
    ['name','price','category','collection','preferred','budget','status','price_source','link'],
    ['Mask','$600','Collectibles','','','big','','',''],
    ['Book','$100','Books','','','','','',''],
    ['Below threshold','$99.99','Books','','','','','',''],
    ['Box','','Music','Record series','yes','big','','shopify','https://shop.test/products/box'],
    ['One','$25','Music','Record series','','small','','',''],
    ['Two','$30','Music','Record series','','small','claimed','',''],
    ['Other A','$20','Music','Other series','','','','',''],
    ['Other B','$15','Music','Other series','','','','',''],
    ['Unknown','','Books','','','','','',''],
    ['Foreign','$500 CAD','Books','','','','','',''],
    ['Already bought','$900','Music','','','big','bought','','']
  ].map(row => row.join(',')).join('\n');
  const boxPrices = {version:1,items:{'https://shop.test/products/box':{...fresh,amount:400,availability:'out_of_stock'}}};
  const sections = await page(sectionCSV,{view:'sections',prices:boxPrices});
  const section = id => sections.nodes.grid.children.find(node => node.id === 'section-' + id);
  assert.deepEqual(sections.nodes.grid.children.map(n => n.id), ['section-big','section-small','section-unknown','section-claimed']);
  assert.deepEqual(cardNames(section('big')), ['Mask','Book','Box','One']);
  assert.deepEqual(cardNames(section('small')), ['Below threshold','Other A','Other B']);
  assert.deepEqual(cardNames(section('unknown')), ['Unknown','Foreign']);
  assert.deepEqual(cardNames(section('claimed')), ['Already bought','Two']);
  assert.equal(cardNames(sections.nodes.grid).length,11, 'Each item appears once, including collapsed alternatives');
  assert.equal(sections.nodes['section-nav'].hidden,false);
  assert.ok(walk(section('big')).some(n => n.textContent === '$400.00 USD'));
  assert.ok(walk(section('big')).some(n => n.className === 'stock'));
  assert.ok(!walk(section('big')).find(n => n.className === 'alternatives').open);
  const details = walk(section('big')).find(n => n.className === 'alternatives');
  details.open = true; details.ontoggle(); sections.run('render()');
  assert.ok(walk(section('big')).find(n => n.className === 'alternatives').open, 'Refresh preserves an open collection');
  const one = walk(section('big')).find(n => n.id === 'item-one');
  await walk(one).find(n => n.className === 'button claim').onclick();
  assert.ok(cardNames(section('claimed')).includes('One'), 'Tentative marks move collection members to the bottom');
  assert.ok(!cardNames(section('big')).includes('One'));
  await walk(section('claimed')).find(n => n.textContent === 'Undo my mark').onclick();
  assert.ok(cardNames(section('big')).includes('One'));
  sections.nodes.categories.children.find(c => c.textContent === 'Books').onclick();
  assert.deepEqual(cardNames(sections.nodes.grid), ['Book','Below threshold','Unknown','Foreign']);
  assert.ok(!section('claimed'), 'Empty sections disappear after filtering');
  sections.nodes.categories.children[0].onclick();
  sections.nodes.sort.value='low'; sections.nodes.sort.onchange();
  assert.equal(sections.nodes.grid.className,'grid');
  assert.equal(sections.nodes['section-nav'].hidden,true);
  assert.deepEqual(cardNames(sections.nodes.grid).slice(0,3),['Other B','Other A','One']);
  assert.deepEqual(cardNames(sections.nodes.grid).slice(-2),['Two','Already bought']);
  const groupedAnchor = await page(sectionCSV,{view:'sections',prices:boxPrices,hash:'#item-one'});
  assert.ok(walk(groupedAnchor.nodes.grid).find(n => n.className === 'alternatives').open);
  assert.ok(walk(groupedAnchor.nodes.grid).find(n => n.id === 'item-one').scrolled);
  groupedAnchor.nodes.categories.children.find(c => c.textContent === 'Books').onclick();
  groupedAnchor.run('revealAnchor()');
  assert.ok(walk(groupedAnchor.nodes.grid).find(n => n.id === 'item-one').scrolled, 'A deep link clears a conflicting filter');
  groupedAnchor.run('priceFeed["https://shop.test/products/box"] = {...priceFeed["https://shop.test/products/box"],amount:89,availability:"available"};render()');
  assert.ok(!walk(groupedAnchor.nodes.grid).some(n => n.className === 'stock'), 'Restock clears the sold-out label');
  assert.deepEqual(cardNames(groupedAnchor.nodes.grid.children.find(n => n.id === 'section-small')),['Below threshold','Box','One','Other A','Other B'], 'Current USD price overrides the usual budget for the whole collection');
  groupedAnchor.run('claims=["item-box"];render()');
  assert.ok(walk(groupedAnchor.nodes.grid).some(n => n.textContent.startsWith('The preferred choice is already marked.')));
  const expiredStock = await page(sectionCSV,{view:'sections',prices:{version:1,items:{'https://shop.test/products/box':{...fresh,amount:400,availability:'out_of_stock',expires_at:new Date(now-1).toISOString()}}}});
  assert.ok(!walk(expiredStock.nodes.grid).some(n => n.className === 'stock'));
  assert.ok(!walk(expiredStock.nodes.grid).some(n => n.textContent === '$400.00 USD'));
  const sectionsLegacy = await page(legacyCSV,{view:'sections'});
  assert.equal(sectionsLegacy.nodes.sort.value,'priority');
  assert.equal(sectionsLegacy.nodes.grid.children.length,1);
  const ownerSections = await page(csv,{view:'sections'});
  const epicCollection = walk(ownerSections.nodes.grid).find(n => n.className === 'collection' && n.attrs['aria-label'] === 'EPIC: The Musical');
  assert.equal(cardNames(epicCollection).length,10);
  assert.equal(cardNames(epicCollection)[0],'EPIC 9 LP Mega Box Set');
  assert.equal(walk(epicCollection).find(n => n.className === 'alternatives').children[0].textContent,'See alternatives (9)');
  assert.ok(walk(epicCollection).find(n => n.className === 'product').href.includes('epic-9-lp-mega-box-set?currency=USD'));
  assert.equal(cardNames(ownerSections.nodes.grid).length,actualItems.length);
  console.log('PASS: budget sections/boundaries; collection integrity; preferred choices and alternatives; actual EPIC grouping; claims last; filters; flat sorting; deep-link expansion; open-state persistence; restock and expired availability; legacy default order.');
  live.run('Date.now = () => ' + (now + 26*3600000));
  live.intervals.find(timer => timer.delay === 30000).fn();
  assert.ok(!walk(live.nodes.grid).some(n => n.textContent === '$249.99 USD'));
  assert.ok(walk(live.nodes.grid).some(n => n.textContent === 'Check price on Amazon'));
  console.log('PASS: fresh feed prices/currencies/timestamps; affiliate URLs; live-price sorting with claims last; stale/invalid/missing feed fallbacks; expiry in long-open tabs; variable prices; legacy manual prices.');
  console.log('PASS: owner data preserved; current and legacy five-column rendering; reordered headers; quoted/multiline CSV; priority and both price sorts; missing prices last; statuses last; ribbons/stamps; filters; theme default/persistence/storage denial; shared tentative claims/undo; optional mailto; clipboard/fallback; unique slugs/deep links; empty/failure states.');
  console.log('Evidence: offline Node VM with a minimal DOM and stubbed CSV fetch. This is not browser/console or visual verification.');
})().catch(error => { console.error(error); process.exitCode=1; });
