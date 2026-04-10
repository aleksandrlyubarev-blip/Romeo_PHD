import { Router, type IRouter } from "express";
import healthRouter from "./health";
import pipelineRouter from "./pipeline";
import mriRouter from "./mri";

const router: IRouter = Router();

router.use(healthRouter);
router.use(pipelineRouter);
router.use(mriRouter);

export default router;
