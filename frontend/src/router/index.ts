import { createRouter, createWebHistory } from "vue-router";

import CompareView from "@/views/CompareView.vue";
import HistoryView from "@/views/HistoryView.vue";
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
  ],
});

export default router;
