import sys
from sets import Set
from intspan import intspan
from itertools import groupby, chain
from pavfinder.splice.novel_splice_finder import check_splice_motif

class Mapping:

    header = ('contig',
              'gene',
              'transcript',
              'coverage'
              )
    
    """Mapping per alignment"""
    def __init__(self, contig, align_blocks, transcripts=[]):
	self.contig = contig
	self.transcripts = transcripts
	self.genes = list(Set([txt.gene for txt in self.transcripts]))
	self.align_blocks = align_blocks
	# coverage for each transcript in self.transcripts
	self.coverages = []
	self.junction_mappings = []
	self.junction_depth = {}
	
    def overlap(self):
	"""Overlaps alignment spans with exon-spans of each matching transcripts
	Upates self.coverages
	"""
	align_span = self.create_span(self.align_blocks)
	
	for transcript in self.transcripts:
	    exon_span = self.create_span(transcript.exons)
	    olap = exon_span.intersection(align_span)
	    self.coverages.append(float(len(olap)) / float(len(exon_span)))
	    
    @staticmethod
    def create_span(blocks):
	"""Creates intspan for each block
	Used by self.overlap()
	"""
	span = None
	for block in blocks:
	    try:
		span = span.union(intspan('%s-%s' % (block[0], block[1])))
	    except:
		span = intspan('%s-%s' % (block[0], block[1]))
		
	return span
    
    def as_tab(self):
	"""Generates tab-delimited line for each mapping"""
	data = []
	data.append(self.contig)
	if self.transcripts:
	    data.append(','.join([gene for gene in Set([txt.gene for txt in self.transcripts])]))
	    data.append(','.join([txt for txt in Set([txt.id for txt in self.transcripts])]))
	else:
	    data.append('-')
	    data.append('-')
	    
	if self.coverages:
	    data.append(','.join(['%.2f' % olap for olap in self.coverages]))
	else:
	    data.append('-')
	
	return '\t'.join(map(str, data))
	
    @staticmethod
    def pick_best(mappings, align, debug=False):
	"""Selects best mapping among transcripts"""
	scores = {}
	metrics = {}
	for transcript, matches in mappings:
	    metric = {'score': 0,
	              'from_edge': 0,
	              'txt_size': 0
	              }
	    # points are scored for matching exon boundaries
	    score = 0
	    for i in range(len(matches)):
		if matches[i] is None:
		    continue
		
		if i == 0:			    
		    if matches[i][0][1][0] == '=':
			score += 5
		    elif matches[i][0][1][0] == '>':
			score += 2
			
		elif i == len(matches) - 1:
		    if matches[i][-1][1][1] == '=':
			score += 5
		    elif matches[i][-1][1][1] == '<':
			score += 2
			
		if matches[i][0][1][1] == '=':
		    score += 4
		if matches[i][-1][1][1] == '=':
		    score += 4	
			
	    # points are deducted for events
	    penalty = 0
	    for i in range(len(matches)):
		# block doesn't match any exon
		if matches[i] is None:
		    penalty += 2
		    continue
		    
		# if one block is mapped to >1 exon
		if len(matches[i]) > 1:
		    penalty += 1
		
		# if consecutive exons are not mapped to consecutive blocks
		if i < len(matches) - 1 and matches[i + 1] is not None:
		    if matches[i + 1][0][0] != matches[i][-1][0] + 1:
			#print 'penalty', matches[i][-1][0], matches[i + 1][0][0]
			penalty += 1
			
	    metric['score'] = score - penalty
	    
	    # if the first or last block doesn't have matches, won't be able to calculate distance from edges
	    # in that case, will set the distance to 'very big'
	    if matches[0] is None or matches[-1] is None:
		metric['from_edge'] = 10000
	    else:
		if transcript.strand == '+':
		    start_exon_num = matches[0][0][0] + 1
		    end_exon_num = matches[-1][-1][0] + 1
		else:
		    start_exon_num = transcript.num_exons() - matches[0][0][0]
		    end_exon_num = transcript.num_exons() - matches[-1][-1][0]
		    
		metric['from_edge'] = align.tstart - transcript.exon(start_exon_num)[0] + align.tend - transcript.exon(end_exon_num)[1]
		    
	    metric['txt_size'] = transcript.length()
	    metrics[transcript] = metric
	    
	    if debug:
		sys.stdout.write("mapping %s %s %s %s %s %s\n" % (align.query, transcript.id, transcript.gene, score, penalty, metric))
	    
	transcripts_sorted = sorted(metrics.keys(), key = lambda txt: (-1 * metrics[txt]['score'], metrics[txt]['from_edge'], metrics[txt]['txt_size']))
	if debug:
	    for t in transcripts_sorted:
		sys.stdout.write('sorted %s %s\n' % (t.id, metrics[t]))
	    	    
	best_transcript = transcripts_sorted[0]
	best_matches = [mapping[1] for mapping in mappings if mapping[0] == best_transcript]
	best_mapping = Mapping(align.query,
	                       align.blocks,
                               [transcripts_sorted[0]],
                               )
	best_mapping.overlap()
	
	return best_mapping
	    	
    @staticmethod
    def group(all_mappings):
	"""Group mappings by gene"""
	gene_mappings = []
	for gene, group in groupby(all_mappings, lambda m: m.genes[0]):
	    mappings = list(group)
	    contigs = ','.join([mapping.contig for mapping in mappings])
	    transcripts = [mapping.transcripts for mapping in mappings]
	    align_blocks = [mapping.align_blocks for mapping in mappings]
	    
	    align_blocks = None
	    
	    for mapping in mappings:
		try:
		    align_blocks = align_blocks.union(Mapping.create_span(mapping.align_blocks))
		except:
		    align_blocks = Mapping.create_span(mapping.align_blocks)		
	    
	    gene_mappings.append(Mapping(contigs,
	                                 align_blocks.ranges(),
	                                 list(Set(chain(*transcripts))),
	                                 )
	                         )
	    	    
	[mapping.overlap() for mapping in gene_mappings]
	return gene_mappings
    
    @classmethod
    def output(cls, mappings, outfile):
	"""Output mappings into output file"""
	out = open(outfile, 'w')
	out.write('%s\n' % '\t'.join(cls.header))
	for mapping in mappings:
	    out.write('%s\n' % mapping.as_tab())
	out.close()

    def map_junctions(self, align, ref_fasta):
	"""Map genome junction coordinates to contig junction coordinates

	This is for reporting read depth of all "valid"(GTAG) mapped junctions
	"""
	strand = self.transcripts[0].strand
	for i in range(len(align.blocks) - 1):
	    genome_jn = ('%s:%d' % (align.target, align.blocks[i][1]), 
	                 '%s:%d' % (align.target, align.blocks[i + 1][0]))
	    contig_jn = (align.query_blocks[i][1], align.query_blocks[i + 1][0])

	    intron_bounds = [align.blocks[i][1] + 1, align.blocks[i + 1][0] - 2]
	    if strand == '-':
		intron_bounds.reverse()

	    # only capture GT-AG junctions (other gaps are assumed deletions)
	    if check_splice_motif(align.target, intron_bounds[0], intron_bounds[1], strand, ref_fasta):
		self.junction_mappings.append((genome_jn, contig_jn))
		# initialize junction depth
		self.junction_depth[genome_jn] = 0

    @classmethod
    def pool_junction_depths(cls, mappings):
	"""Group junction coverage from each mapping(per alignment) and sum them

	Assumption: read-to-contig alignment is not multi-mappped
	"""
	all_depths = {}
	for mapping in mappings:
	    for (genome_jn, depth) in mapping.junction_depth.iteritems():
		chrom, start = genome_jn[0].split(':')
		if not all_depths.has_key(chrom):
		    all_depths[chrom] = {}
		end = genome_jn[1].split(':')[1]
		try:
		    all_depths[chrom][(start, end)] += depth
		except:
		    all_depths[chrom][(start, end)] = depth

	return all_depths

    @classmethod
    def output_junctions(cls, junction_depths, out_file):
	"""Output junction coverages in BED format"""
	out = open(out_file, 'w')
	for chrom in sorted(junction_depths.keys()):
	    for (start, end) in junction_depths[chrom].keys():
		depth = junction_depths[chrom][(start, end)]
		data = []
		data.append(chrom)
		data.append(int(start) - 1)
		data.append(end)
		data.append(depth)
		data.append(depth)
		data.append('.')
		data.append(int(start) - 1)
		data.append(end)
		data.append(0)
		data.append(2)
		data.append('1,1')
		data.append('%s,%s' % (0, int(end) - 1 - (int(start) - 1)))
		out.write('%s\n' % '\t'.join(map(str, data)))
	out.close()
