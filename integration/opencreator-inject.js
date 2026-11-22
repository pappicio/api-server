(() => {
    'use strict';

    const DASHBOARD_URL = `${window.location.protocol}//${window.location.hostname}:8765/`;
    const ROOT_ID = 'opencreator-integration';

    function initialize() {
        const existingRoot = document.getElementById(ROOT_ID);
        const existingHost = document.getElementById('opencreator-frame-host');

        if (existingRoot && existingHost) return true;

        existingRoot?.remove();
        existingHost?.remove();

        let toolbar;
        let main;
        let wrapper;
        let original;

        if (document.querySelector('#page-container')) {
            toolbar = document.querySelector('header.topbar .v-toolbar__content');
            main = document.querySelector('#content.v-main');
            wrapper = document.querySelector('#content .v-main__wrap');
            original = document.querySelector('#page-container');
        } else {
            main = document.querySelector('main.v-main');
            wrapper = main?.querySelector('.v-main__wrap');
            original = wrapper?.querySelector(':scope > .container');
            toolbar = document.querySelector('.v-app-bar .v-toolbar__content');
        }

        if (!toolbar || !main || !wrapper || !original) return false;

        const root = document.createElement('div');
        root.id = ROOT_ID;

        const style = document.getElementById(`${ROOT_ID}-style`)
            || document.createElement('style');
        style.id = `${ROOT_ID}-style`;
        style.textContent = `
            #${ROOT_ID} {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                margin-left: 12px;
                z-index: 20;
            }
            #${ROOT_ID} button {
                border: 0;
                border-radius: 4px;
                padding: 7px 12px;
                color: #fff;
                background: transparent;
                font: inherit;
                font-size: 14px;
                cursor: pointer;
            }
            #${ROOT_ID} button:hover,
            #${ROOT_ID} button.active {
                background: rgba(255,255,255,.16);
            }
            #opencreator-frame-host {
                display: none;
                position: absolute;
                inset: 0;
                z-index: 5;
                min-height: calc(100vh - 84px);
                background: #121212;
            }
            #opencreator-frame-host iframe {
                display: block;
                width: 100%;
                height: 100%;
                min-height: calc(100vh - 84px);
                border: 0;
            }
        `;
        document.head.appendChild(style);

        const openButton = document.createElement('button');
        openButton.type = 'button';
        openButton.textContent = 'OpenCreator';

        const printerButton = document.createElement('button');
        printerButton.type = 'button';
        printerButton.textContent = 'Printer';
        printerButton.style.display = 'none';

        root.append(openButton, printerButton);
        toolbar.appendChild(root);

        const host = document.createElement('div');
        host.id = 'opencreator-frame-host';

        const iframe = document.createElement('iframe');
        iframe.src = DASHBOARD_URL;
        iframe.title = 'OpenCreator Dashboard';

        host.appendChild(iframe);
        wrapper.appendChild(host);

        const originalDisplay = original.style.display;
        wrapper.style.position = 'relative';

        function showDashboard(show) {
            original.style.display = show ? 'none' : originalDisplay;
            host.style.display = show ? 'block' : 'none';

            openButton.classList.toggle('active', show);
            printerButton.style.display = show ? '' : 'none';
            openButton.setAttribute('aria-pressed', String(show));
        }

        openButton.addEventListener('click', () => showDashboard(true));
        printerButton.addEventListener('click', () => showDashboard(false));

        console.info('[OpenCreator] Integration initialized');
        return true;
    }

    initialize();

    const observer = new MutationObserver(() => {
        const root = document.getElementById(ROOT_ID);
        const host = document.getElementById('opencreator-frame-host');

        if (!root || !host) initialize();
    });

    observer.observe(document.documentElement, {
        childList: true,
        subtree: true
    });
})();
