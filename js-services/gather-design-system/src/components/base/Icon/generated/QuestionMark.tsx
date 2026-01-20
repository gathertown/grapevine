import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgQuestionMark = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M12 13.1163L14.3752 11.7967C15.5605 11.1383 16.2957 9.88889 16.2957 8.53293C16.1553 6.27807 14.2215 4.55912 11.9657 4.68401C9.95011 4.60034 8.16024 5.96286 7.70428 7.92801" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /><path d="M12.1792 18.5988C12.1791 18.6976 12.099 18.7776 12.0002 18.7775C11.9014 18.7775 11.8213 18.6974 11.8213 18.5986C11.8212 18.4998 11.9012 18.4197 12 18.4196C12.0476 18.4195 12.0932 18.4384 12.1268 18.472C12.1604 18.5056 12.1793 18.5512 12.1792 18.5988" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgQuestionMark);
export default Memo;