import { Router, type IRouter } from "express";
import healthRouter from "./health";
import pipelineRouter from "./pipeline";
import inspectionsRouter from "./inspections";

const router: IRouter = Router();

router.use(healthRouter);
router.use(pipelineRouter);
router.use(inspectionsRouter);

export default router;
