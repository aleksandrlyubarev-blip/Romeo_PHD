import { Router, type IRouter } from "express";
import healthRouter from "./health";
import pipelineRouter from "./pipeline";
import filmittoRouter from "./filmitto";

const router: IRouter = Router();

router.use(healthRouter);
router.use(pipelineRouter);
router.use(filmittoRouter);

export default router;
