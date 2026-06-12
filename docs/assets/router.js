/**
 * Hash-based router. Pages register themselves; navigation is instant.
 */

const Router = (() => {
  const pages = [];     // { id, label, render(target) }
  let currentId = null;

  function register(page) {
    pages.push(page);
  }

  function buildNav() {
    const nav = document.getElementById('nav');
    nav.innerHTML = '';
    let lastGroup = null;
    pages.forEach(p => {
      if (p.group && p.group !== lastGroup) {
        const h = document.createElement('div');
        h.className = 'nav-group';
        h.textContent = p.group;
        h.style.cssText = 'font-size:10px;font-weight:600;text-transform:uppercase;'
                        + 'letter-spacing:.08em;color:#a1a1aa;margin:18px 12px 4px';
        nav.appendChild(h);
        lastGroup = p.group;
      } else if (!p.group) {
        lastGroup = null;
      }
      const a = document.createElement('a');
      a.href = '#/' + p.id;
      a.textContent = p.label;
      a.dataset.id = p.id;
      a.addEventListener('click', (e) => {
        e.preventDefault();
        navigate(p.id);
      });
      nav.appendChild(a);
    });
  }

  function setActive(id) {
    document.querySelectorAll('#nav a').forEach(a => {
      a.classList.toggle('active', a.dataset.id === id);
    });
  }

  function navigate(id) {
    if (!pages.some(p => p.id === id)) id = pages[0].id;
    window.location.hash = '#/' + id;
  }

  function render() {
    const hash = window.location.hash || '';
    const m = hash.match(/^#\/([\w-]+)/);
    const id = (m && m[1]) || pages[0].id;
    const page = pages.find(p => p.id === id) || pages[0];

    if (currentId === page.id) return;   // already showing
    currentId = page.id;
    setActive(page.id);

    const target = document.getElementById('content');
    target.innerHTML = '';
    UI.showLoader('Loading ' + page.label + '\u2026');

    try {
      Promise.resolve(page.render(target)).then(() => {
        UI.hideLoader();
      }).catch(err => {
        UI.hideLoader();
        target.innerHTML = '';
        target.appendChild(UI.el('div', { class: 'splash' }, 'Failed to load: ' + err.message));
      });
    } catch (err) {
      UI.hideLoader();
      target.innerHTML = '';
      target.appendChild(UI.el('div', { class: 'splash' }, 'Failed to load: ' + err.message));
    }
  }

  function start() {
    buildNav();
    window.addEventListener('hashchange', () => { currentId = null; render(); });
    render();
  }

  return { register, navigate, start };
})();
