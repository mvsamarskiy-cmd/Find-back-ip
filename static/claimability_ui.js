/* Strict claimability presentation.
 *
 * Free-green is reserved for direct claimability. Paid/marketplace inventory is
 * actionable but deliberately rendered as a separate purple state.
 */
(() => {
  function statusOf(row) {
    return normalizedStatus(row);
  }

  uiState = function strictUiState(row) {
    const status = statusOf(row);
    if (status === 'claimable') return { cls: 'free', label: 'Вільне' };
    if (status === 'purchasable') return { cls: 'purchase', label: 'Можна купити' };
    if (conflictStatuses.has(status)) return { cls: 'taken', label: status === 'invalid' ? 'Недопустиме' : 'Зайняте' };
    if (status === 'not_found') return { cls: 'unknown', label: 'Не знайдено' };
    return { cls: 'unknown', label: 'Не вдалося підтвердити' };
  };

  allGreen = function strictAllGreen(row) {
    const resources = Array.isArray(current?.resources) ? current.resources : [];
    return resources.length > 0 && resources.every(
      key => statusOf((row.availability || {})[key]) === 'claimable',
    );
  };

  function hasPurchase(row) {
    const resources = Array.isArray(current?.resources) ? current.resources : [];
    return resources.some(key => statusOf((row.availability || {})[key]) === 'purchasable');
  }

  badgeLabel = function strictBadgeLabel(row) {
    if (allGreen(row)) return 'вільне підтверджено';
    if (hasConflict(row)) return 'є конфлікт';
    if (hasPurchase(row)) return 'можна купити';
    if (row?.bundle_state === 'promising') return 'перспективний';
    return 'перевірка завершена';
  };

  if (!document.getElementById('claimabilityUiStyle')) {
    const style = document.createElement('style');
    style.id = 'claimabilityUiStyle';
    style.textContent = '.check.purchase .dot{background:#a979ff}.check.purchase .state{color:#c7a9ff}';
    document.head.appendChild(style);
  }

  try { render(); } catch (_) {}
})();
