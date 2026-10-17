const filters = [...document.querySelectorAll('[data-filter]')];
const projects = [...document.querySelectorAll('[data-category]')];
for (const button of filters) button.addEventListener('click', () => {
  for (const other of filters) other.setAttribute('aria-pressed', String(other === button));
  let count = 0;
  for (const project of projects) {
    project.hidden = button.dataset.filter !== 'all' && project.dataset.category !== button.dataset.filter;
    if (!project.hidden) count++;
  }
  document.querySelector('#project-count').textContent = String(count);
});
