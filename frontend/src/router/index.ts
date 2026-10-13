import { createRouter, createWebHistory } from "vue-router";

import CompareView from "@/views/CompareView.vue";
import HistoryView from "@/views/HistoryView.vue";
import NotFoundView from "@/views/NotFoundView.vue";
import ParseView from "@/views/ParseView.vue";
import ReportView from "@/views/ReportView.vue";
import UploadView from "@/views/UploadView.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "upload", component: UploadView },
    { path: "/parse", name: "parse", component: ParseView },
    { path: "/report/:id?", name: "report", component: ReportView },
    { path: "/compare", name: "compare", component: CompareView },
    { path: "/history", name: "history", component: HistoryView },
    // 兜底：未知地址此前会落到一个空白页（router-view 无匹配），刷新手输地址时尤其容易遇到
    { path: "/:pathMatch(.*)*", name: "not-found", component: NotFoundView },
  ],
});

export default router;
