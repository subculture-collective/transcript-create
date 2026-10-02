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
    ? (matches ? `${matches} matching ${matches === 1 ? 'word' : 'words'} in this example.` : 'No matches here. Try “context” or “source”.')
    : 'Three passages. One continuous conversation.';
});
passages.forEach((passage) => passage.addEventListener('click', () => {
  passages.forEach((item) => {
    item.classList.toggle('selected', item === passage);
    item.setAttribute('aria-pressed', String(item === passage));
  });
  document.querySelector('#selection-status').textContent = `SELECTED / ${passage.dataset.time}`;
}));
