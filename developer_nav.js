(function() {
    const style = document.createElement('style');
    style.textContent = `
        .nav-badge {
            position: relative;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 16px;
            height: 16px;
            border-radius: 50%;
            color: #fff;
            font-size: 10px;
            line-height: 1;
            font-weight: 700;
            margin-left: 6px;
            overflow: visible;
            isolation: isolate;
        }
        .nav-badge-new { background: linear-gradient(135deg, #d9363e, #f56c6c); }
        .nav-badge-up { background: linear-gradient(135deg, #1c7ffd, #5ba8ff); }
        .nav-badge::before {
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            width: 100%;
            height: 100%;
            border-radius: 50%;
            transform: translate(-50%, -50%);
            opacity: 0;
            animation: nav-badge-pulse 1.5s ease-out infinite;
            z-index: -1;
        }
        .nav-badge-new::before { background: linear-gradient(135deg, #d9363e, #f56c6c); }
        .nav-badge-up::before { background: linear-gradient(135deg, #1c7ffd, #5ba8ff); }
        @keyframes nav-badge-pulse {
            0% {
                transform: translate(-50%, -50%) scale(1);
                opacity: 0.6;
            }
            100% {
                transform: translate(-50%, -50%) scale(1.5);
                opacity: 0;
            }
        }
    `;
    document.head.appendChild(style);
})();

const developerTopNavItems = [
    { id: 'workbench', label: '工作台', href: 'admin_workbench.html' },
    { id: 'resource_mgmt', label: '资源中心', href: 'catalog_manage.html?nav=resource-catalog' },
    { id: 'supply_demand', label: '供需中心', href: 'scene_center.html?nav=demand-scene' },
    { id: 'objection', label: '异议中心', href: 'objection_accept.html?nav=objection-accept', disabled: true },
    { id: 'monitor', label: '监控中心', href: 'monitor_dashboard.html?nav=monitor-dashboard' },
    { id: 'statistics', label: '统计中心', href: 'statistics_dashboard.html?nav=statistics-dashboard' },
    { id: 'config', label: '配置中心', href: 'config_center.html?nav=config-scene' }
];

const developerSideNavMap = {
    workbench: [
        { type: 'link', label: '工作台', href: 'admin_workbench.html', navKey: 'workbench-admin', icon: 'fa-chart-line' }
    ],
    resource_mgmt: [
        {
            type: 'group',
            label: '目录管理',
            icon: 'fa-list',
            badge: '升',
            children: [
                { type: 'link', label: '目录编制', href: 'catalog_manage.html?nav=resource-catalog', navKey: 'resource-catalog', badge: '升' },
                { type: 'link', label: '目录审核', href: 'catalog_audit.html?nav=resource-catalog-audit', navKey: 'resource-catalog-audit', badge: '升' },
                { type: 'link', label: '已发布目录', href: 'data_update.html?nav=resource-catalog-update', navKey: 'resource-catalog-update', badge: '升' },
                { type: 'link', label: '数据更新审核', href: 'data_update_audit.html?nav=resource-catalog-update-audit', navKey: 'resource-catalog-update-audit', badge: '升' }
            ]
        },
        {
            type: 'group',
            label: '服务管理',
            icon: 'fa-server',
            badge: '升',
            children: [
                { type: 'link', label: '服务注册', href: 'service_register.html?nav=resource-service', navKey: 'resource-service', badge: '升' },
                { type: 'link', label: '服务审核', href: 'service_audit.html?nav=resource-service-audit', navKey: 'resource-service-audit', badge: '升' },
                { type: 'link', label: '服务交付', href: 'service_delivery.html?nav=resource-service-delivery', navKey: 'resource-service-delivery', badge: '升' }
            ]
        }
    ],
    supply_demand: [
        {
            type: 'group',
            label: '需求管理',
            icon: 'fa-file-signature',
            badge: '升',
            children: [
                { type: 'link', label: '场景管理', href: 'scene_center.html?nav=demand-scene', navKey: 'demand-scene', badge: '升' },
                { type: 'link', label: '我的需求', disabled: true }
            ]
        },
        {
            type: 'group',
            label: '供给管理',
            icon: 'fa-handshake',
            children: [
                { type: 'link', label: '需求审核', disabled: true },
                { type: 'link', label: '需求交付', disabled: true },
                { type: 'link', label: '我的供给', disabled: true }
            ]
        },
        {
            type: 'group',
            label: '供需管理',
            icon: 'fa-scale-balanced',
            badge: '升',
            children: [
                { type: 'link', label: '需求受理', href: 'demand_accept.html?nav=demand-accept', navKey: 'demand-accept', badge: '升' },
                { type: 'link', label: '扩容审核', disabled: true }
            ]
        }
    ],
    objection: [
        {
            type: 'group',
            label: '异议管理',
            icon: 'fa-circle-exclamation',
            collapsed: true,
            children: [
                { type: 'link', label: '异议提出', disabled: true },
                { type: 'link', label: '异议受理', href: 'objection_accept.html?nav=objection-accept', navKey: 'objection-accept' },
                { type: 'link', label: '异议核查', disabled: true },
                { type: 'link', label: '异议审查', disabled: true },
                { type: 'link', label: '异议评价', disabled: true },
                { type: 'link', label: '我收到的评价', disabled: true }
            ]
        },
        {
            type: 'group',
            label: '数据质量管理',
            icon: 'fa-chart-line',
            children: [
                { type: 'link', label: '数据质量反馈', disabled: true },
                { type: 'link', label: '数据质量核查', disabled: true },
                { type: 'link', label: '数据质量审查', disabled: true }
            ]
        }
    ],
    approval: [
        {
            type: 'group',
            label: '已发起',
            icon: 'fa-paper-plane',
            children: [
                { type: 'link', label: '数据申请工单', href: 'data_resource_apply.html?nav=initiated-resource', navKey: 'initiated-resource' },
                { type: 'link', label: '配额申请工单', href: 'quota_apply_work_order.html?nav=initiated-quota', navKey: 'initiated-quota' }
            ]
        },
        {
            type: 'group',
            label: '待处理',
            icon: 'fa-clock',
            children: [
                { type: 'link', label: '数据资源审核', href: 'data_resource_audit.html?nav=pending-resource', navKey: 'pending-resource' },
                { type: 'link', label: '配额分配审核', href: 'quota_audit.html?nav=pending-quota', navKey: 'pending-quota' }
            ]
        }
    ],
    statistics: [
        { type: 'link', label: '统计看板', href: 'statistics_dashboard.html?nav=statistics-dashboard', navKey: 'statistics-dashboard', icon: 'fa-chart-pie', badge: '新' },
        {
            type: 'group',
            label: '目录服务统计',
            icon: 'fa-table',
            children: [
                { type: 'link', label: '目录服务总览', href: '', navKey: 'statistics-overview', disabled: true },
                { type: 'link', label: '部门目录基本情况', href: '', navKey: 'statistics-dept-catalog', disabled: true },
                { type: 'link', label: '区划目录基本情况', href: '', navKey: 'statistics-region-catalog', disabled: true },
                { type: 'link', label: '部门服务基本情况', href: '', navKey: 'statistics-dept-service', disabled: true },
                { type: 'link', label: '区划服务基本情况', href: '', navKey: 'statistics-region-service', disabled: true }
            ]
        },
        {
            type: 'group',
            label: '申请使用统计',
            icon: 'fa-file-circle-check',
            badge: '新',
            children: [
                { type: 'link', label: '部门申请服务情况', href: '', navKey: 'statistics-dept-apply', disabled: true },
                { type: 'link', label: '区划申请服务情况', href: '', navKey: 'statistics-region-apply', disabled: true },
                { type: 'link', label: '部门服务被申请情况', href: '', navKey: 'statistics-dept-applied', disabled: true },
                { type: 'link', label: '区划服务被申请情况', href: '', navKey: 'statistics-region-applied', disabled: true },
                { type: 'link', label: '服务被调用情况', href: '', navKey: 'statistics-service-called', disabled: true },
                { type: 'link', label: '部门调用情况', href: '', navKey: 'statistics-dept-call', disabled: true },
                { type: 'link', label: '区划调用情况', href: '', navKey: 'statistics-region-call', disabled: true },
                { type: 'link', label: '部门接口调用情况', href: '', navKey: 'statistics-dept-api-call', disabled: true },
                { type: 'link', label: '需求数据量', href: 'statistics_demand.html?nav=statistics-demand', navKey: 'statistics-demand', badge: '新' }
            ]
        },
        { type: 'link', label: '基础库统计', href: '', navKey: 'statistics-database', disabled: true, icon: 'fa-database' },
        { type: 'link', label: '数据归集查询', href: '', navKey: 'statistics-data-collection', disabled: true, icon: 'fa-database' },
        { type: 'link', label: '清单中心', href: '', navKey: 'statistics-inventory-center', disabled: true, icon: 'fa-list-check' }
    ],
    config: [
        {
            type: 'group',
            label: '配置管理',
            icon: 'fa-sliders',
            badge: '新',
            children: [
                { type: 'link', label: '场景配置', href: 'config_center.html?nav=config-scene', navKey: 'config-scene', badge: '新' }
            ]
        }
    ],
    monitor: [
        { type: 'link', label: '监控看板', href: 'monitor_dashboard.html?nav=monitor-dashboard', navKey: 'monitor-dashboard', icon: 'fa-chart-pie', badge: '新' },
        {
            type: 'group',
            label: '服务使用监控',
            icon: 'fa-eye',
            children: [
                { type: 'link', label: '供给服务监控', href: 'monitor_service_monitor.html?nav=monitor-service-monitor', navKey: 'monitor-service-monitor' },
                { type: 'link', label: '申请服务监控', href: '', navKey: 'monitor-apply-monitor', disabled: true },
                { type: 'link', label: '场景使用监控', href: '', navKey: 'monitor-scene-monitor', disabled: true },
                { type: 'link', label: '服务使用监控', href: '', navKey: 'monitor-service-usage', disabled: true }
            ]
        },
        {
            type: 'group',
            label: '服务使用告警',
            icon: 'fa-bell',
            badge: '新',
            children: [
                { type: 'link', label: '供给服务告警', href: '', navKey: 'monitor-service-alarm', disabled: true },
                { type: 'link', label: '申请服务告警', href: '', navKey: 'monitor-apply-alarm', disabled: true },
                { type: 'link', label: '服务异常告警', href: '', navKey: 'monitor-exception-alarm', disabled: true },
                { type: 'link', label: '授权提醒处置', href: 'monitor_authorization_alert.html?nav=monitor-authorization-alert', navKey: 'monitor-authorization-alert', badge: '新' }
            ]
        },
        { type: 'link', label: '心跳检测', href: '', navKey: 'monitor-heartbeat', disabled: true, icon: 'fa-heartbeat' }
    ],
    help: [
        { type: 'link', label: '帮助中心', href: 'help_center.html?nav=help', navKey: 'help', icon: 'fa-circle-question' }
    ]
};

const developerPathDefaults = {
    'index.html': { group: 'workbench', navKey: 'workbench-admin' },
    'admin_workbench.html': { group: 'workbench', navKey: 'workbench-admin' },
    'data_resource_apply.html': { group: 'approval', navKey: 'initiated-resource' },
    'quota_apply_work_order.html': { group: 'approval', navKey: 'initiated-quota' },
    'quota_audit.html': { group: 'approval', navKey: 'pending-quota' },
    'scene_center.html': { group: 'supply_demand', navKey: 'demand-scene' },
    'demand_accept.html': { group: 'supply_demand', navKey: 'demand-accept' },
    'objection_accept.html': { group: 'objection', navKey: 'objection-accept' },
    
    'statistics_dashboard.html': { group: 'statistics', navKey: 'statistics-dashboard' },
    'statistics_demand.html': { group: 'statistics', navKey: 'statistics-demand' },
    'config_center.html': { group: 'config', navKey: 'config-scene' },
    'scene_add.html': { group: 'config', navKey: 'config-scene' },
    'monitor_service_monitor.html': { group: 'monitor', navKey: 'monitor-service-monitor' },
    'monitor_dashboard.html': { group: 'monitor', navKey: 'monitor-dashboard' },
    'monitor_authorization_alert.html': { group: 'monitor', navKey: 'monitor-authorization-alert' },
    'help_center.html': { group: 'help', navKey: 'help' },
    'data_resource_audit.html': { group: 'approval', navKey: 'pending-resource' },
    'catalog_manage.html': { group: 'resource_mgmt', navKey: 'resource-catalog' },
    'catalog_add.html': { group: 'resource_mgmt', navKey: 'resource-catalog' },
    'catalog_audit.html': { group: 'resource_mgmt', navKey: 'resource-catalog-audit' },
    'data_update_audit.html': { group: 'resource_mgmt', navKey: 'resource-catalog-update-audit' },
    'catalog_tables.html': { group: 'resource_mgmt', navKey: 'resource-catalog-tables' },
    'service_register.html': { group: 'resource_mgmt', navKey: 'resource-service' },
    'service_register_add.html': { group: 'resource_mgmt', navKey: 'resource-service' },
    'service_audit.html': { group: 'resource_mgmt', navKey: 'resource-service-audit' },
    'service_delivery.html': { group: 'resource_mgmt', navKey: 'resource-service-delivery' },
    'service_delivery_add.html': { group: 'resource_mgmt', navKey: 'resource-service-delivery' }
};

const developerNavKeyToGroup = {};

Object.keys(developerSideNavMap).forEach((groupId) => {
    developerSideNavMap[groupId].forEach((item) => {
        if (item.type === 'group') {
            item.children.forEach((child) => {
                developerNavKeyToGroup[child.navKey] = groupId;
            });
            return;
        }
        developerNavKeyToGroup[item.navKey] = groupId;
    });
});

function getDeveloperNavState() {
    const url = new URL(window.location.href);
    const currentPath = window.location.pathname.split('/').pop() || 'index.html';
    const currentNav = url.searchParams.get('nav');
    const fallback = developerPathDefaults[currentPath] || developerPathDefaults['index.html'];
    const activeGroup = currentNav ? (developerNavKeyToGroup[currentNav] || fallback.group) : fallback.group;
    const activeNav = currentNav || fallback.navKey;

    return {
        currentPath,
        activeGroup,
        activeNav
    };
}

function renderDeveloperTopNav(state) {
    const legacyContainer = document.getElementById('developer-top-nav');
    if (legacyContainer) {
        legacyContainer.classList.add('hidden');
    }

    const header = document.querySelector('body > header');
    if (!header || !header.firstElementChild || !header.lastElementChild) {
        return;
    }

    const headerLeft = header.firstElementChild;
    const headerRight = header.lastElementChild;

    header.classList.remove('justify-between');
    header.classList.add('gap-6');
    headerLeft.classList.add('flex-1', 'min-w-0');
    headerRight.classList.add('shrink-0');

    let container = document.getElementById('developer-header-top-nav');
    if (!container) {
        container = document.createElement('div');
        container.id = 'developer-header-top-nav';
        container.className = 'ml-8 flex items-center gap-2 overflow-x-auto whitespace-nowrap';
        headerLeft.appendChild(container);
    }

    container.innerHTML = developerTopNavItems.map((item) => {
            const isActive = item.id === state.activeGroup;
            // 临时隐藏审批中心、帮助中心（保留代码，后续可恢复）
            const hiddenStyle = (item.id === 'approval' || item.id === 'help') ? ' style="display:none"' : '';
            if (item.disabled) {
                return `
                    <span${hiddenStyle}
                        class="px-4 h-[34px] inline-flex items-center rounded-md border transition-colors whitespace-nowrap text-[14px] opacity-50 cursor-not-allowed border-transparent text-white/80"
                    >
                        ${item.label}
                    </span>
                `;
            }
            if (!item.href) {
                return `
                    <span${hiddenStyle}
                        class="px-4 h-[34px] inline-flex items-center rounded-md border transition-colors whitespace-nowrap text-[14px] cursor-default ${
                                isActive
                                    ? 'bg-white/18 border-white/30 text-white font-medium shadow-sm'
                                    : 'border-transparent text-white/80'
                        }"
                    >
                        ${item.label}
                    </span>
                `;
            }
            return `
                <a${hiddenStyle}
                    href="${item.href}"
                    class="px-4 h-[34px] inline-flex items-center rounded-md border transition-colors whitespace-nowrap text-[14px] ${
                            isActive
                                ? 'bg-white/18 border-white/30 text-white font-medium shadow-sm'
                                : 'border-transparent text-white/80 hover:text-white hover:bg-white/10'
                    }"
                >
                    ${item.label}
                </a>
            `;
        }).join('');
}

window.toggleNavGroup = function(groupId) {
    const content = document.getElementById(`nav-group-content-${groupId}`);
    const arrow = document.getElementById(`nav-group-arrow-${groupId}`);
    if (content.classList.contains('hidden')) {
        content.classList.remove('hidden');
        arrow.classList.remove('fa-angle-right');
        arrow.classList.add('fa-angle-down');
    } else {
        content.classList.add('hidden');
        arrow.classList.remove('fa-angle-down');
        arrow.classList.add('fa-angle-right');
    }
};

function renderDeveloperNavItem(item, state, isChild = false) {
    const isActive = item.navKey === state.activeNav;
    const paddingClass = isChild ? 'pl-11 pr-4 py-2.5' : 'px-4 py-3';
    const textClass = isChild ? 'text-[13px]' : 'text-[14px] font-medium';
    
    const iconHtml = !isChild && item.icon ? `<i class="fa-solid ${item.icon} w-5 text-center mr-2 text-lg"></i>` : '';
    const badgeClass = item.badge === '新' ? 'nav-badge nav-badge-new' : item.badge === '升' ? 'nav-badge nav-badge-up' : '';
    const badgeHtml = item.badge ? `<span class="${badgeClass}">${item.badge}</span>` : '';

    if (item.disabled) {
        return `
            <div
                class="flex items-center ${paddingClass} text-[#c0c4cc] cursor-not-allowed transition-colors rounded-lg mx-2 my-0.5"
                title="暂无页面"
            >
                ${iconHtml}
                <span>${item.label}</span>
                ${badgeHtml}
            </div>
        `;
    }

    return `
        <a
            href="${item.href}"
            class="flex items-center ${paddingClass} transition-colors rounded-lg mx-2 my-0.5 ${
                isActive
                    ? 'bg-blue-50 text-[#1c7ffd]'
                    : 'text-[#606266] hover:text-[#1c7ffd] hover:bg-gray-50'
            } ${textClass}"
        >
            ${iconHtml}
            <span>${item.label}</span>
            ${badgeHtml}
        </a>
    `;
}

function renderDeveloperSideNav(state) {
    const container = document.getElementById('developer-side-nav');
    if (!container) {
        return;
    }

    const sections = developerSideNavMap[state.activeGroup] || [];

    container.innerHTML = `
        <div class="flex flex-col py-2">
            ${sections.map((item, index) => {
                if (item.type === 'group') {
                    const groupActive = item.children.some((child) => child.navKey === state.activeNav);
                    const groupExpanded = groupActive && !item.collapsed;
                    const groupId = `group-${index}`;
                    const groupBadgeClass = item.badge === '新' ? 'nav-badge nav-badge-new' : item.badge === '升' ? 'nav-badge nav-badge-up' : '';
                    const groupBadgeHtml = item.badge ? `<span class="${groupBadgeClass}">${item.badge}</span>` : '';
                    
                    return `
                        <div class="flex flex-col mb-1">
                            <div 
                                class="flex items-center justify-between px-4 py-3 mx-2 rounded-lg cursor-pointer transition-colors ${groupActive ? 'text-[#1c7ffd]' : 'text-[#303133] hover:bg-gray-50'} font-medium text-[14px]"
                                onclick="toggleNavGroup('${groupId}')"
                            >
                                <div class="flex items-center">
                                    <i class="fa-solid ${item.icon || 'fa-folder'} w-5 text-center mr-2 text-lg"></i>
                                    <span>${item.label}</span>
                                    ${groupBadgeHtml}
                                </div>
                                <i id="nav-group-arrow-${groupId}" class="fa-solid ${groupExpanded ? 'fa-angle-down' : 'fa-angle-right'} text-gray-400 text-xs transition-transform duration-200"></i>
                            </div>
                            <div id="nav-group-content-${groupId}" class="flex flex-col mt-0.5 ${groupExpanded ? '' : 'hidden'}">
                                ${item.children.map((child) => renderDeveloperNavItem(child, state, true)).join('')}
                            </div>
                        </div>
                    `;
                }
                return `<div class="mb-1">${renderDeveloperNavItem(item, state, false)}</div>`;
            }).join('')}
        </div>
    `;
}

document.addEventListener('DOMContentLoaded', () => {
    try {
        const state = getDeveloperNavState();
        renderDeveloperTopNav(state);
        renderDeveloperSideNav(state);
    } catch (e) {
        document.body.innerHTML += '<div style="color:red;z-index:9999;position:fixed;top:0;left:0;background:white;padding:20px;">' + e.toString() + ' ' + e.stack + '</div>';
    }
});
