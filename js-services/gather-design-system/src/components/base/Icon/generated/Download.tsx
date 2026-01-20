import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgDownload = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M20.7498 15.0931V18.5931C20.7498 19.6977 19.8544 20.5931 18.7498 20.5931H6.24976C5.14519 20.5931 4.24976 19.6977 4.24976 18.5931V15.0931M12.4998 15.3431V4.09314M12.4998 15.3431L8.99976 11.8431M12.4998 15.3431L15.9998 11.8431" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgDownload);
export default Memo;