// Optional compatibility for cloud sandboxes without /proc/self.
// RSS fallback is the actual process peak RSS; heap statistics come from V8.
// Regular hosts must not enable this preload. arrayBuffers unavailable here.
const v8 = require('node:v8');
const original = process.memoryUsage;
function fallback() {
 const heap=v8.getHeapStatistics();
 return {rss:process.resourceUsage().maxRSS*1024, heapTotal:heap.total_heap_size,
  heapUsed:heap.used_heap_size, external:heap.external_memory, arrayBuffers:0};
}
process.memoryUsage = function() {
 try{return original()}catch(error){if(error.code!=='ENOENT')throw error;return fallback()}
};
process.memoryUsage.rss = function() {
 try{return original.rss()}catch(error){if(error.code!=='ENOENT')throw error;return fallback().rss}
};
