// 门户通用组件 - 头部、底部、悬浮按钮
(function() {
    // 导航菜单配置
    const navItems = [
        { key: 'home', label: '首页', href: 'index.html', badge: '升' },
        { key: 'data_center', label: '数据中心', href: 'portal_data_center.html', badge: '升' },
        { key: 'scene_center', label: '场景中心', href: 'portal_scene_center.html', badge: '新' },
        { key: 'app_center', label: '应用中心', href: 'portal_app_center.html', badge: '升' },
        { key: 'material_center', label: '资料中心', href: 'portal_material_center.html', badge: '升' },
        { key: 'work_dynamics', label: '工作动态', href: 'portal_work_dynamics.html', badge: '升' }
    ];

    // 目录类型
    const catalogTypes = [
        { name: '共享目录', icon: 'fa-folder-open' },
        { name: '可信目录', icon: 'fa-shield-halved' },
        { name: '登记目录', icon: 'fa-clipboard-list' }
    ];

    let currentCatalog = '共享目录';

    // 渲染头部
    function renderHeader(activeKey) {
        if (!document.getElementById('portal-badge-style')) {
            const styleEl = document.createElement('style');
            styleEl.id = 'portal-badge-style';
            styleEl.textContent = `
                .portal-badge {
                    position: absolute;
                    top: 8px;
                    right: 2px;
                    min-width: 16px;
                    height: 16px;
                    padding: 0 4px;
                    border-radius: 8px;
                    color: #fff;
                    font-size: 10px;
                    font-weight: 700;
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    line-height: 1;
                    isolation: isolate;
                }
                .portal-badge::before {
                    content: '';
                    position: absolute;
                    inset: 0;
                    border-radius: 8px;
                    opacity: 0.55;
                    z-index: -1;
                    animation: portal-badge-pulse 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite;
                }
                .portal-badge-new {
                    background: linear-gradient(135deg, #d9363e, #f56c6c);
                }
                .portal-badge-new::before {
                    background: linear-gradient(135deg, #d9363e, #f56c6c);
                }
                .portal-badge-up {
                    background: linear-gradient(135deg, #1c7ffd, #5ba8ff);
                }
                .portal-badge-up::before {
                    background: linear-gradient(135deg, #1c7ffd, #5ba8ff);
                }
                @keyframes portal-badge-pulse {
                    0% { transform: scale(1); opacity: 0.55; }
                    100% { transform: scale(1.5); opacity: 0; }
                }
            `;
            document.head.appendChild(styleEl);
        }

        const header = `
    <header class="fixed top-0 left-0 right-0 h-16 bg-white border-b border-gray-200 shadow-sm z-50">
        <div class="max-w-[1440px] mx-auto h-full flex items-center justify-between px-6">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg gradient-bg flex items-center justify-center">
                    <i class="fa-solid fa-database text-white text-xl"></i>
                </div>
                <span class="text-xl font-bold text-[#1c7ffd] tracking-wide">数据服务平台</span>
                <div class="relative ml-2 catalog-dropdown">
                    <button class="flex items-center gap-2 px-3 py-1.5 bg-blue-50 hover:bg-blue-100 rounded-md text-[#1c7ffd] text-sm transition-colors" onclick="PortalCommon.toggleCatalogDropdown()">
                        <span id="current-catalog">${currentCatalog}</span>
                        <i class="fa-solid fa-chevron-down text-xs"></i>
                    </button>
                    <div class="absolute left-0 top-full mt-1 w-32 bg-white rounded-lg shadow-lg border border-gray-100 py-1 z-50 opacity-0 invisible transform translate-y-2 transition-all duration-200 catalog-dropdown-menu">
                        ${catalogTypes.map(c => `
                        <button class="w-full flex items-center gap-2 px-4 py-2 text-sm ${c.name === currentCatalog ? 'text-[#1c7ffd] bg-blue-50' : 'text-[#606266]'} hover:bg-blue-100 transition-colors" onclick="PortalCommon.selectCatalog('${c.name}')">
                            <i class="fa-solid ${c.icon} text-xs"></i>
                            ${c.name}
                        </button>
                        `).join('')}
                    </div>
                </div>
            </div>
            <nav class="flex items-center gap-1">
                ${navItems.map(item => {
                    const isActive = activeKey === item.key;
                    const badgeClass = item.badge === '新' ? 'portal-badge portal-badge-new' : item.badge === '升' ? 'portal-badge portal-badge-up' : '';
                    const badgeHtml = item.badge ? `<span class="${badgeClass}">${item.badge}</span>` : '';
                    return `
                <a href="${item.href}" class="px-5 h-16 flex items-center ${isActive ? 'text-[#1c7ffd] font-medium border-b-2 border-[#1c7ffd]' : 'text-[#606266] hover:text-[#1c7ffd]'} text-[15px] transition-colors relative">
                    ${item.label}
                    ${badgeHtml}
                </a>
                `;
                }).join('')}
            </nav>
            <div class="flex items-center gap-4">
                <div class="relative user-dropdown">
                    <button class="flex items-center gap-2 px-3 py-2 hover:bg-gray-50 rounded-lg transition-colors cursor-pointer">
                        <div class="w-8 h-8 rounded-full gradient-bg flex items-center justify-center">
                            <i class="fa-solid fa-user text-white text-sm"></i>
                        </div>
                        <span class="text-sm font-medium text-[#303133]">admin</span>
                        <i class="fa-solid fa-angle-down text-xs text-[#909399]"></i>
                    </button>
                    <div class="absolute right-0 top-full mt-1 w-40 bg-white rounded-lg shadow-lg border border-gray-100 py-1 z-50 opacity-0 invisible transform translate-y-2 transition-all duration-200 user-dropdown-menu">
                        <a href="admin_workbench.html" class="flex items-center gap-3 px-4 py-2.5 text-sm text-[#606266] hover:bg-gray-50 hover:text-[#1c7ffd] transition-colors">
                            <i class="fa-solid fa-gear text-xs"></i>
                            <span>进入后台</span>
                        </a>
                        <div class="border-t border-gray-100 my-1"></div>
                        <button onclick="PortalCommon.logout()" class="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-[#606266] hover:bg-gray-50 hover:text-red-500 transition-colors">
                            <i class="fa-solid fa-right-from-bracket text-xs"></i>
                            <span>退出登录</span>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </header>
        `;
        document.write(header);
    }

    // 渲染底部
    function renderFooter() {
        const footer = `
    <footer class="bg-[#1c2025] text-white py-12">
        <div class="max-w-[1440px] mx-auto px-6">
            <div class="grid md:grid-cols-2 gap-10 mb-8">
                <div>
                    <div class="flex items-center gap-3 mb-4">
                        <div class="w-10 h-10 rounded-lg gradient-bg flex items-center justify-center">
                            <i class="fa-solid fa-database text-white text-xl"></i>
                        </div>
                        <span class="text-xl font-bold">数据服务平台</span>
                    </div>
                    <p class="text-[#8f959e] text-sm leading-relaxed max-w-sm">
                        一站式数据服务平台，汇聚海量数据资源，提供高效数据处理能力，助力企业数字化转型与创新发展。
                    </p>
                </div>
                <div class="grid sm:grid-cols-2 gap-10">
                    <div>
                        <h4 class="font-semibold mb-4">快速链接</h4>
                        <ul class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm text-[#8f959e]">
                            <li><a href="index.html" class="hover:text-white transition-colors">首页</a></li>
                            <li><a href="portal_data_center.html" class="hover:text-white transition-colors">数据中心</a></li>
                            <li><a href="portal_scene_center.html" class="hover:text-white transition-colors">场景中心</a></li>
                            <li><a href="portal_app_center.html" class="hover:text-white transition-colors">应用中心</a></li>
                            <li><a href="portal_material_center.html" class="hover:text-white transition-colors">资料中心</a></li>
                            <li><a href="portal_work_dynamics.html" class="hover:text-white transition-colors">工作动态</a></li>
                        </ul>
                    </div>
                    <div>
                        <h4 class="font-semibold mb-4">联系我们</h4>
                        <ul class="space-y-3 text-sm text-[#8f959e]">
                            <li class="flex items-center gap-2"><i class="fa-solid fa-map-marker text-[#1c7ffd]"></i>山东省济南市高新区</li>
                            <li class="flex items-center gap-2"><i class="fa-solid fa-phone text-[#1c7ffd]"></i>400-888-8888</li>
                            <li class="flex items-center gap-2"><i class="fa-solid fa-envelope text-[#1c7ffd]"></i>support@example.com</li>
                        </ul>
                    </div>
                </div>
            </div>
            <div class="border-t border-gray-700 pt-6 flex flex-col items-center justify-center text-sm text-[#8f959e]">
                <p>Copyright 2026 数据服务平台 版权所有</p>
            </div>
        </div>
    </footer>
        `;
        document.write(footer);
    }

    // 渲染悬浮按钮
    function renderFloatButtons() {
        const buttons = `
    <button class="fixed bottom-40 right-8 z-50 group" title="数据篮" onclick="window.location.href='data_basket.html'">
        <div class="relative">
            <div class="w-16 h-16 rounded-full bg-white border-2 border-[#1c7ffd] flex items-center justify-center shadow-lg hover:shadow-xl transition-all duration-300 group-hover:scale-110">
                <i class="fa-solid fa-basket-shopping text-[#1c7ffd] text-2xl"></i>
            </div>
            <div class="absolute -top-1 -right-1 w-5 h-5 bg-red-500 rounded-full border-2 border-white flex items-center justify-center">
                <span class="text-white text-[10px] font-bold">1</span>
            </div>
            <div class="absolute right-full mr-3 top-1/2 -translate-y-1/2 bg-[#1c2025] text-white text-sm px-3 py-2 rounded-lg whitespace-nowrap opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-300">
                数据篮
                <div class="absolute right-0 top-1/2 -translate-y-1/2 translate-x-1 w-2 h-2 bg-[#1c2025] rotate-45"></div>
            </div>
        </div>
    </button>

    <button class="fixed bottom-20 right-8 z-50 group" title="智能问答助手" onclick="window.location.href='smart_chat.html'">
        <div class="relative">
            <div class="w-16 h-16 rounded-full flex items-center justify-center shadow-lg hover:shadow-xl transition-all duration-300 group-hover:scale-110" style="background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 50%, #a78bfa 100%);">
                <i class="fa-solid fa-robot text-white text-2xl"></i>
            </div>
            <div class="absolute right-full mr-3 top-1/2 -translate-y-1/2 bg-[#1c2025] text-white text-sm px-3 py-2 rounded-lg whitespace-nowrap opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-300">
                智能问答助手
                <div class="absolute right-0 top-1/2 -translate-y-1/2 translate-x-1 w-2 h-2 bg-[#1c2025] rotate-45"></div>
            </div>
        </div>
    </button>
        `;
        document.write(buttons);
    }

    // 目录下拉切换
    function toggleCatalogDropdown() {
        const menu = document.querySelector('.catalog-dropdown-menu');
        menu.classList.toggle('opacity-0');
        menu.classList.toggle('invisible');
        menu.classList.toggle('translate-y-2');
    }

    function selectCatalog(name) {
        currentCatalog = name;
        const el = document.getElementById('current-catalog');
        if (el) el.textContent = name;
        toggleCatalogDropdown();
    }

    // 退出登录
    function logout() {
        alert('已退出登录');
    }

    // 初始化下拉菜单hover事件
    function initDropdowns() {
        // 用户下拉菜单
        const userDropdown = document.querySelector('.user-dropdown');
        if (userDropdown) {
            const menu = userDropdown.querySelector('.user-dropdown-menu');
            userDropdown.addEventListener('mouseenter', function() {
                menu.classList.remove('opacity-0', 'invisible', 'translate-y-2');
            });
            userDropdown.addEventListener('mouseleave', function() {
                menu.classList.add('opacity-0', 'invisible', 'translate-y-2');
            });
        }

        // 目录下拉
        const catalogDropdown = document.querySelector('.catalog-dropdown');
        if (catalogDropdown) {
            const menu = catalogDropdown.querySelector('.catalog-dropdown-menu');
            catalogDropdown.addEventListener('mouseenter', function() {
                menu.classList.remove('opacity-0', 'invisible', 'translate-y-2');
            });
            catalogDropdown.addEventListener('mouseleave', function() {
                menu.classList.add('opacity-0', 'invisible', 'translate-y-2');
            });
        }

        // 点击外部关闭
        document.addEventListener('click', function(e) {
            const catalogDropdown = document.querySelector('.catalog-dropdown');
            if (catalogDropdown && !catalogDropdown.contains(e.target)) {
                const menu = catalogDropdown.querySelector('.catalog-dropdown-menu');
                if (menu) menu.classList.add('opacity-0', 'invisible', 'translate-y-2');
            }
        });
    }

    // 页面加载完成后初始化
    document.addEventListener('DOMContentLoaded', initDropdowns);

    // 暴露全局API
    window.PortalCommon = {
        renderHeader,
        renderFooter,
        renderFloatButtons,
        toggleCatalogDropdown,
        selectCatalog,
        logout
    };
})();
