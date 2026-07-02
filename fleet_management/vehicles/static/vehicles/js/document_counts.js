// Fetch document counts and update the counts in the documents list page
(function(){
    const ajaxUrl = '/documents/counts/';

    async function fetchCounts(){
        try{
            const res = await fetch(ajaxUrl, { credentials: 'same-origin' });
            if(!res.ok) return;
            const data = await res.json();
            const map = {
                'count-vehicle': data.vehicle_document_count,
                'count-company': data.company_document_count,
                'count-equipment': data.equipment_document_count,
                'count-all': data.total_document_count,
                'count-expired': data.expired_count,
                'count-expiring': data.expiring_count,
                'count-safe': data.safe_count,
                'count-total': data.total_document_count,
                'vehicle-doc-count': data.vehicle_document_count,
            };
            Object.keys(map).forEach(id => {
                const el = document.getElementById(id);
                if(el) el.textContent = map[id];
            });
        }catch(e){
            // fail silently
            console.warn('document_counts fetch failed', e);
        }
    }

    async function fetchDocumentData(){
        try{
            const res = await fetch('/documents/data/' + window.location.search, { credentials: 'same-origin' });
            if(!res.ok) return;
            const payload = await res.json();
            payload.documents.forEach(doc => {
                const row = document.querySelector(`tr[data-document-id="${doc.id}"]`);
                if(!row) return;
                const numEl = row.querySelector('.doc-number');
                const issuingEl = row.querySelector('.doc-issuing');
                const locEl = row.querySelector('.doc-location');
                const assetEl = row.querySelector('.doc-asset');
                const expiryEl = row.querySelector('.doc-expiry');
                const statusEl = row.querySelector('.doc-status');
                const respEl = row.querySelector('.doc-responsible');
                const daysEl = row.querySelector('.doc-days');

                if(numEl) numEl.textContent = doc.document_number || '';
                if(issuingEl) issuingEl.textContent = doc.issuing_authority ? ('Issued by: ' + doc.issuing_authority) : '';
                if(locEl) locEl.textContent = doc.location ? ('Location: ' + doc.location) : '';
                if(assetEl){
                    if(doc.asset && doc.asset.url){
                        assetEl.innerHTML = `<a href="${doc.asset.url}">${doc.asset.name}${doc.asset.license_plate ? ' ('+doc.asset.license_plate+')' : ''}</a>`;
                    } else if(doc.asset){
                        assetEl.textContent = doc.asset.name;
                    } else {
                        assetEl.textContent = 'Company-wide';
                    }
                }
                if(expiryEl) expiryEl.textContent = doc.expiry_date ? new Date(doc.expiry_date).toLocaleDateString() : '';
                if(statusEl) statusEl.innerHTML = doc.status === 'expired' ? '<span class="badge bg-danger">❌ Expired</span>' : (doc.status === 'expiring' ? '<span class="badge bg-warning">⚠️ Expiring Soon</span>' : '<span class="badge bg-success">✅ Valid</span>');
                if(respEl) respEl.textContent = doc.responsible || '';
                if(daysEl) daysEl.textContent = doc.days_until_expiry !== null && doc.days_until_expiry !== undefined ? (doc.days_until_expiry + ' days') : '';
            });
        }catch(e){
            console.warn('document data fetch failed', e);
        }
    }

    // Fetch both counts and document data on load
    if(document.readyState === 'loading'){
        document.addEventListener('DOMContentLoaded', () => { fetchCounts(); fetchDocumentData(); });
    } else {
        fetchCounts(); fetchDocumentData();
    }

    if(document.readyState === 'loading'){
        document.addEventListener('DOMContentLoaded', fetchCounts);
    } else {
        fetchCounts();
    }
})();
