(function () {
    document.addEventListener('DOMContentLoaded', function () {
        document.getElementById('btn-backup') &&
            document.getElementById('btn-backup').addEventListener('click', function () {
                var json = EstithmarStore.exportState();
                var blob = new Blob([json], { type: 'application/json' });
                var a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = 'estithmar-backup-' + new Date().toISOString().slice(0, 10) + '.json';
                a.click();
                URL.revokeObjectURL(a.href);
            });

        document.getElementById('btn-import') &&
            document.getElementById('btn-import').addEventListener('click', function () {
                var f = document.getElementById('import-file').files[0];
                if (!f) {
                    alert('Choose a JSON file.');
                    return;
                }
                var r = new FileReader();
                r.onload = function () {
                    try {
                        EstithmarStore.importState(r.result);
                        alert('Import complete. Reloading.');
                        location.reload();
                    } catch (e) {
                        alert('Invalid file: ' + e.message);
                    }
                };
                r.readAsText(f);
            });

        document.getElementById('btn-reset') &&
            document.getElementById('btn-reset').addEventListener('click', function () {
                if (!confirm('Clear all local data and reload?')) return;
                EstithmarStore.resetAll();
                location.reload();
            });
    });
})();
