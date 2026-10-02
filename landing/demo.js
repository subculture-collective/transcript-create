const search = document.querySelector('#demo-search');
const passages = [...document.querySelectorAll('.passage')];
const originals = passages.map((passage) => passage.querySelector('.passage-copy').textContent);
search.addEventListener('input', () => {
  const query = search.value.trim().toLocaleLowerCase();
  let matches = 0;
  passages.forEach((passage, index) => {
    const copy = passage.querySelector('.passage-copy');
    const text = originals[index];
    copy.replaceChildren();
    let cursor = 0;
    let hit = query ? text.toLocaleLowerCase().indexOf(query) : -1;
    while (hit !== -1) {
      copy.append(document.createTextNode(text.slice(cursor, hit)));
      const mark = document.createElement('mark');
      mark.textContent = text.slice(hit, hit + query.length);
      copy.append(mark);
      matches++;
      cursor = hit + query.length;
      hit = text.toLocaleLowerCase().indexOf(query, cursor);
    }
    copy.append(document.createTextNode(text.slice(cursor)));
  });
  document.querySelector('#search-status').textContent = query
    ? (matches ? `${matches} matching ${matches === 1 ? 'word' : 'words'} in this example.` : 'No matches here. Try “broadcasting” or “people”.')
    : 'Three transcript segments from the same recording.';
});
passages.forEach((passage) => passage.addEventListener('click', () => {
  passages.forEach((item) => {
    item.classList.toggle('selected', item === passage);
    item.setAttribute('aria-pressed', String(item === passage));
  });
  document.querySelector('#selection-status').textContent = `SELECTED / ${passage.dataset.time}`;
  const source = document.querySelector('#source-link');
  source.href = passage.dataset.sourceUrl;
  source.textContent = `Open source at ${passage.dataset.time} ↗`;
  document.querySelector('#copy-status').textContent = '';
  document.querySelector('#copy-passage').textContent = 'Copy passage link';
}));

document.querySelector('#copy-passage').addEventListener('click', async () => {
  const selected = document.querySelector('.passage.selected');
  const status = document.querySelector('#copy-status');
  try {
    await navigator.clipboard.writeText(selected.dataset.passageUrl);
    status.textContent = `Passage link copied for ${selected.dataset.time}.`;
    document.querySelector('#copy-passage').textContent = 'Link copied';
  } catch {
    status.replaceChildren(document.createTextNode('Clipboard unavailable. Copy this link: '));
    const link = document.createElement('a');
    link.href = selected.dataset.passageUrl;
    link.textContent = selected.dataset.passageUrl;
    status.append(link);
  }
});
