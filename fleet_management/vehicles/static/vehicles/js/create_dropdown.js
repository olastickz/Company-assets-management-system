(function(){
    const btn = document.getElementById('dashboardCreateDropdownBtn');
    const menu = document.getElementById('dashboardCreateDropdownMenu');
    const docBtn = document.getElementById('dashboardDocSubmenuBtn');
    const docSub = document.getElementById('dashboardDocSubmenu');

    function closeAll(e){
        if (!menu) return;
        if (!menu.contains(e.target) && e.target !== btn) {
            menu.style.display = 'none';
            if (docSub) {
                docSub.style.display = 'none';
                docBtn?.setAttribute('aria-expanded','false');
            }
            btn?.setAttribute('aria-expanded','false');
        }
    }

    function toggleMenu(open) {
        if (!menu) return;
        const isOpen = menu.style.display === 'block';
        const targetState = (typeof open === 'boolean') ? open : !isOpen;
        menu.style.display = targetState ? 'block' : 'none';
        btn?.setAttribute('aria-expanded', String(targetState));
        if (!targetState && docSub) {
            docSub.style.display = 'none';
            docBtn?.setAttribute('aria-expanded', 'false');
        }
    }

    btn?.addEventListener('click', function(e){
        e.stopPropagation();
        toggleMenu();
    });

    btn?.addEventListener('keydown', function(e){
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            toggleMenu();
        } else if (e.key === 'Escape') {
            toggleMenu(false);
            btn.focus();
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            toggleMenu(true);
            const first = menu.querySelector('[role="menuitem"]');
            first?.focus();
        }
    });

    docBtn?.addEventListener('click', function(e){
        e.stopPropagation();
        if (!docSub) return;
        const open = docSub.style.display === 'block';
        docSub.style.display = open ? 'none' : 'block';
        docBtn.setAttribute('aria-expanded', String(!open));
    });

    docBtn?.addEventListener('keydown', function(e){
        if (!docSub) return;
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            docBtn.click();
        } else if (e.key === 'Escape') {
            docSub.style.display = 'none';
            docBtn.setAttribute('aria-expanded', 'false');
            docBtn.focus();
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            const first = docSub.querySelector('[role="menuitem"]');
            first?.focus();
        }
    });

    document.addEventListener('click', closeAll);
    document.addEventListener('keydown', function(e){
        if (e.key === 'Escape') {
            toggleMenu(false);
        }
    });
})();
