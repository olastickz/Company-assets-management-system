(function(){
    // Lightweight staff autocomplete module
    function debounce(fn, wait){ let t; return function(){ const args=arguments; clearTimeout(t); t=setTimeout(()=>fn.apply(this,args), wait); }; }

    function createAutocompleteForSelect(select){
        if(!select) return;
        // hide original select
        select.style.display = 'none';

        // create input
        const input = document.createElement('input');
        input.type = 'search';
        input.className = select.className || 'form-control';
        input.placeholder = select.getAttribute('data-placeholder') || 'Search staff by ID, name, or branch...';
        input.autocomplete = 'off';
        select.parentNode.insertBefore(input, select.nextSibling);

        // suggestion box
        const container = document.createElement('div');
        container.style.position = 'relative';
        select.parentNode.insertBefore(container, input.nextSibling);
        const box = document.createElement('div');
        box.style.position = 'absolute'; box.style.left = 0; box.style.right = 0; box.style.background = 'white'; box.style.border = '1px solid #ccc'; box.style.zIndex = 60; box.style.display = 'none';
        container.appendChild(box);

        function setSelected(id,label){
            input.value = label;
            select.value = id;
        }

        // initialize with current option
        const sel = select.options[select.selectedIndex];
        if(sel && sel.value){ input.value = sel.text; }

        const endpoint = (select.getAttribute('data-autocomplete-url') || '/api/staff-autocomplete/');

        const fetchResults = debounce(function(q){
            if(!q || q.length < 1){ box.style.display = 'none'; return; }
            fetch(endpoint + '?q=' + encodeURIComponent(q), {credentials: 'same-origin'})
                .then(r=>r.json())
                .then(data=>{
                    box.innerHTML = '';
                    if(!data || !data.length){ box.style.display = 'none'; return; }
                    data.forEach(item=>{
                        const row = document.createElement('div');
                        row.textContent = item.label;
                        row.style.padding = '8px 12px';
                        row.style.cursor = 'pointer';
                        row.addEventListener('click', function(){ setSelected(item.id, item.label); box.style.display = 'none'; });
                        box.appendChild(row);
                    });
                    box.style.display = 'block';
                }).catch(()=>{ box.style.display = 'none'; });
        }, 180);

        input.addEventListener('input', function(){ fetchResults(this.value.trim()); });
        document.addEventListener('click', function(e){ if(!container.contains(e.target) && e.target !== input) box.style.display = 'none'; });
    }

    document.addEventListener('DOMContentLoaded', function(){
        // Find all selects that opted in via data-autocomplete="staff"
        const selects = document.querySelectorAll('select[data-autocomplete="staff"]');
        selects.forEach(s => createAutocompleteForSelect(s));
    });
})();
