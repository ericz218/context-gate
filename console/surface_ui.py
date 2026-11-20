"""Surface hierarchy: a section owns the only frame; content inside it uses rows or tints."""

CSS = r'''
/* surface-hierarchy: 外框只属于 section，内层用分隔线或浅底区分 */
:root[data-theme] main :is(#workbench,#gt-list,section) :is(.wb-item,.quota-log-row){margin:0;border:0;border-bottom:1px solid var(--line);border-radius:0;background:none;box-shadow:none;transform:none}
:root[data-theme] main :is(#workbench,#gt-list,section) :is(.wb-item,.quota-log-row):last-child{border-bottom:0}
:root[data-theme] main :is(#workbench,#gt-list,section) :is(.wb-item,.quota-log-row):hover{background:var(--rowhover);box-shadow:none;transform:none}
:root[data-theme] main :is(#workbench,#gt-list,section) :is(.wb-item.open,.quota-log-row[open]){border-color:var(--line);border-radius:8px;background:var(--rowhover);box-shadow:none}
:root[data-theme] main :is(#workbench,#gt-list,section) :is(.wb-item.open .wb-head,.quota-log-row[open] summary){border-bottom:0;border-radius:8px}
main section #workbench,main section #gt-list{gap:0}
:root[data-theme] main section :is(.tile,.quota-card){border:0;border-radius:8px;background:var(--chip);box-shadow:none}
:root[data-theme] main section .tile:hover{background:var(--rowhover);box-shadow:none}
:root[data-theme] main section .quota-card{padding:20px}
:root[data-theme] main section :is(#todo-page .todo-import,.memory-export,.router-stats),:root[data-theme] #todo-page .todo-import{border:0;border-radius:8px;background:var(--chip)}
:root[data-theme] #todo-page .todo-list{border:0;border-radius:0;background:none}
:root[data-theme] main :is(section,.ux-advanced) pre{border:0}
'''
