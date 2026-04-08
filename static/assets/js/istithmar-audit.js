(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var tb = document.getElementById('audit-tbody');
        if (!tb) return;
        var rows = IstithmarStore.getAuditLogs();
        tb.innerHTML = rows
            .map(function (l) {
                return (
                    '<tr><td>' +
                    (l.at || '').replace('T', ' ').slice(0, 19) +
                    '</td><td>' +
                    (l.action || '') +
                    '</td><td>' +
                    (l.detail || '') +
                    '</td></tr>'
                );
            })
            .join('');
        if (!rows.length) tb.innerHTML = '<tr><td colspan="3" class="text-muted">No logs.</td></tr>';
    });
})();
