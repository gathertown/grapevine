import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgUploadCloud = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M5.82745 16.0017C3.36686 14.2926 2.36833 11.1392 3.39678 8.32533C4.42522 5.51149 7.22192 3.74515 10.2047 4.02561C13.1874 4.30607 15.6058 6.56277 16.0917 9.51899C16.2318 9.50904 16.3618 9.49899 16.5019 9.49899C18.6942 9.49822 20.5681 11.0773 20.9389 13.2381C21.3098 15.3988 20.0696 17.5124 18.0025 18.2426M15.0013 15.0015L12 12.0003M12 12.0003L8.99877 15.0015M12 12.0003L12 20.0034" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgUploadCloud);
export default Memo;